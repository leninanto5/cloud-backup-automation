"""Restore a backup zip to a folder.

Usage:
    python scripts/restore.py --latest
    python scripts/restore.py backups/my-backup_20261102_020000.zip --to restored
"""
import argparse
import os
import sys
import zipfile

import yaml

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resolve(path):
    return path if os.path.isabs(path) else os.path.normpath(os.path.join(BASE_DIR, path))


def latest_backup():
    with open(os.path.join(BASE_DIR, "config.yaml"), "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    folder = resolve(config["destination"]["local_path"])
    prefix = config["backup_name"] + "_"
    zips = sorted(n for n in os.listdir(folder) if n.startswith(prefix) and n.endswith(".zip"))
    if not zips:
        sys.exit("No backups found in " + folder)
    return os.path.join(folder, zips[-1])


def safe_extract(zip_path, destination):
    destination = os.path.abspath(destination)
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.namelist():
            target = os.path.abspath(os.path.join(destination, member))
            if not target.startswith(destination + os.sep):
                sys.exit(f"Unsafe path in archive: {member}")
        zf.extractall(destination)
        return len(zf.namelist())


def main():
    p = argparse.ArgumentParser(description="Restore a backup archive.")
    p.add_argument("backup", nargs="?", help="path to the backup .zip file")
    p.add_argument("--latest", action="store_true", help="restore the newest local backup")
    p.add_argument("--to", default="restored", help="folder to restore into (default: restored)")
    args = p.parse_args()

    if args.latest:
        zip_path = latest_backup()
    elif args.backup:
        zip_path = resolve(args.backup)
    else:
        sys.exit("Give a backup file or use --latest")

    if not os.path.isfile(zip_path):
        sys.exit(f"Backup not found: {zip_path}")

    destination = resolve(args.to)
    os.makedirs(destination, exist_ok=True)
    count = safe_extract(zip_path, destination)
    print(f"Restored {count} files from {os.path.basename(zip_path)} to {destination}")


if __name__ == "__main__":
    main()
