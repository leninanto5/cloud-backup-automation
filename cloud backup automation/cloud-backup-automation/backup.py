import argparse
import fnmatch
import hashlib
import logging
import os
import shutil
import sys
import tempfile
import time
import zipfile
from datetime import datetime
from string import Template

import yaml

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = os.path.join(BASE_DIR, "config.yaml")
log = logging.getLogger("backup")


# ------------------------------------------------------------ helpers
def resolve(path):
    """Relative paths are resolved from the project folder, so the script
    works from any location (important for scheduled runs)."""
    return path if os.path.isabs(path) else os.path.normpath(os.path.join(BASE_DIR, path))


def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    for key in ("backup_name", "sources", "destination", "retention"):
        if key not in config:
            raise ValueError(f"config.yaml is missing '{key}'")
    return config


def setup_logging(log_file):
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    for handler in (logging.FileHandler(log_file, encoding="utf-8"), logging.StreamHandler()):
        handler.setFormatter(fmt)
        log.addHandler(handler)


def human_size(size):
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# --------------------------------------------------- collecting files
def is_excluded(rel_path, patterns):
    rel = rel_path.replace("\\", "/")
    parts = rel.split("/")
    for pattern in patterns:
        if fnmatch.fnmatch(rel, pattern) or any(fnmatch.fnmatch(p, pattern) for p in parts):
            return True
    return False


def collect_files(sources, exclude):
    """Returns a list of (absolute path, path inside the zip)."""
    files = []
    for source in sources:
        src = resolve(source)
        if not os.path.exists(src):
            log.warning("Source not found, skipping: %s", src)
            continue
        if os.path.isfile(src):
            files.append((src, os.path.basename(src)))
            continue

        root_name = os.path.basename(os.path.normpath(src))
        for folder, dirs, names in os.walk(src):
            rel_folder = os.path.relpath(folder, src)
            dirs[:] = [
                d for d in dirs
                if not is_excluded(d if rel_folder == "." else os.path.join(rel_folder, d), exclude)
            ]
            for name in names:
                rel = name if rel_folder == "." else os.path.join(rel_folder, name)
                if not is_excluded(rel, exclude):
                    files.append((os.path.join(folder, name), os.path.join(root_name, rel)))
    return files


def create_archive(files, archive_path):
    count, total = 0, 0
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for abs_path, arcname in files:
            try:
                zf.write(abs_path, arcname)
                count += 1
                total += os.path.getsize(abs_path)
            except OSError as e:
                log.warning("Skipped %s (%s)", abs_path, e)
    return count, total


# ------------------------------------------------------- destinations
class LocalDestination:
    def __init__(self, cfg):
        self.folder = resolve(cfg["local_path"])
        os.makedirs(self.folder, exist_ok=True)

    def upload(self, file_path, name):
        target = os.path.join(self.folder, name)
        shutil.copy2(file_path, target)
        return target

    def list_backups(self, prefix):
        names = [n for n in os.listdir(self.folder)
                 if n.startswith(prefix + "_") and n.endswith(".zip")]
        return sorted(names)  # timestamp in the name -> oldest first

    def delete(self, name):
        os.remove(os.path.join(self.folder, name))


class S3Destination:
    def __init__(self, cfg):
        try:
            import boto3
        except ImportError:
            raise SystemExit("boto3 is required for S3 backups. Run: pip install boto3")
        s3 = cfg["s3"]
        self.bucket = s3["bucket"]
        self.prefix = s3.get("prefix", "")
        self.client = boto3.client("s3", region_name=s3.get("region"))

    def upload(self, file_path, name):
        key = self.prefix + name
        self.client.upload_file(file_path, self.bucket, key)
        return f"s3://{self.bucket}/{key}"

    def list_backups(self, prefix):
        names = []
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=self.prefix + prefix + "_"):
            for obj in page.get("Contents", []):
                names.append(obj["Key"][len(self.prefix):])
        return sorted(names)

    def delete(self, name):
        self.client.delete_object(Bucket=self.bucket, Key=self.prefix + name)


def get_destination(config):
    dest = config["destination"]
    kind = dest.get("type", "local").lower()
    if kind == "local":
        return LocalDestination(dest)
    if kind == "s3":
        return S3Destination(dest)
    raise ValueError(f"Unknown destination type: {kind}")


def apply_retention(dest, name, keep_last):
    keep_last = max(1, int(keep_last))
    backups = dest.list_backups(name)
    removed = backups[:-keep_last] if len(backups) > keep_last else []
    for old in removed:
        dest.delete(old)
        log.info("Deleted old backup: %s", old)
    return removed


# ------------------------------------------------------------- report
def generate_report(config, data):
    report_cfg = config.get("report", {})
    template_path = resolve(report_cfg.get("template", "templates/report_template.txt"))
    with open(template_path, "r", encoding="utf-8") as f:
        template = Template(f.read())
    text = template.safe_substitute(data)

    folder = resolve(report_cfg.get("save_to", "./backups/reports"))
    os.makedirs(folder, exist_ok=True)
    report_path = os.path.join(folder, f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(text)
    return text, report_path


# --------------------------------------------------------- main logic
def run_backup(config, dry_run=False):
    start = time.time()
    name = config["backup_name"]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_name = f"{name}_{stamp}.zip"

    files = collect_files(config["sources"], config.get("exclude", []))
    if not files:
        raise RuntimeError("No files found to back up. Check 'sources' in config.yaml")

    if dry_run:
        total = sum(os.path.getsize(p) for p, _ in files)
        print(f"Dry run: {len(files)} files ({human_size(total)}) would be backed up.")
        return None

    tmp = tempfile.mkdtemp()
    try:
        archive_path = os.path.join(tmp, archive_name)
        log.info("Creating archive %s ...", archive_name)
        count, original = create_archive(files, archive_path)

        with zipfile.ZipFile(archive_path) as zf:
            if zf.testzip() is not None:
                raise RuntimeError("Archive verification failed (corrupt zip)")

        checksum = sha256_of(archive_path)
        archive_size = os.path.getsize(archive_path)

        dest = get_destination(config)
        location = dest.upload(archive_path, archive_name)
        log.info("Uploaded to %s", location)

        removed = apply_retention(dest, name, config["retention"].get("keep_last", 5))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    saved = (1 - archive_size / original) * 100 if original else 0
    return {
        "files_count": count,
        "original_size": human_size(original),
        "archive_size": human_size(archive_size),
        "compression": f"{saved:.1f}% smaller",
        "archive_name": archive_name,
        "checksum": checksum,
        "location": location,
        "deleted_count": len(removed),
        "duration": f"{time.time() - start:.2f}",
        "notes": "Archive verified successfully",
    }


def run_and_report(config, dry_run=False):
    """Runs the backup, writes the report, and returns True on success."""
    data = {
        "backup_name": config["backup_name"],
        "timestamp": datetime.now().strftime("%d %b %Y, %H:%M:%S"),
    }
    try:
        result = run_backup(config, dry_run)
        if dry_run:
            return True
        data.update(result)
        data["status"] = "SUCCESS"
        ok = True
    except Exception as e:
        log.error("Backup failed: %s", e)
        data.update(status="FAILED", notes=str(e), files_count="-", original_size="-",
                    archive_size="-", compression="-", archive_name="-", checksum="-",
                    location="-", deleted_count="-", duration="-")
        ok = False

    text, path = generate_report(config, data)
    print("\n" + text)
    log.info("Report saved to %s", path)
    return ok


def run_scheduler(config):
    try:
        import schedule
    except ImportError:
        raise SystemExit("The 'schedule' package is required. Run: pip install schedule")

    run_time = config.get("schedule", {}).get("time", "02:00")
    schedule.every().day.at(run_time).do(run_and_report, config)
    log.info("Scheduler started. Backup will run every day at %s (press Ctrl+C to stop)", run_time)
    try:
        while True:
            schedule.run_pending()
            time.sleep(30)
    except KeyboardInterrupt:
        log.info("Scheduler stopped.")


def parse_args():
    p = argparse.ArgumentParser(description="Automated backups to a local folder or Amazon S3.")
    p.add_argument("--config", default=DEFAULT_CONFIG, help="path to config file (default: config.yaml)")
    p.add_argument("--schedule", action="store_true", help="run continuously and back up daily")
    p.add_argument("--list", action="store_true", help="list existing backups")
    p.add_argument("--dry-run", action="store_true", help="show what would be backed up, without backing up")
    return p.parse_args()


def main():
    args = parse_args()
    config = load_config(resolve(args.config))
    setup_logging(resolve(config.get("logging", {}).get("file", "backup.log")))

    if args.list:
        backups = get_destination(config).list_backups(config["backup_name"])
        print("\n".join(backups) if backups else "No backups found.")
    elif args.schedule:
        run_scheduler(config)
    else:
        sys.exit(0 if run_and_report(config, args.dry_run) else 1)


if __name__ == "__main__":
    main()
