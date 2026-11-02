# Cloud Backup Automation

A Python tool that automatically backs up your files into a compressed, verified archive and stores it in a local folder or in **Amazon S3**. It deletes old backups automatically, creates a report after every run, and can run on a daily schedule.

## Features
- Backs up multiple folders and files into one `.zip` archive
- Exclude files and folders using patterns (`*.tmp`, `.git`, ...)
- Archive verification and SHA-256 checksum
- Stores backups locally or in an Amazon S3 bucket
- Automatic retention: keeps only the newest N backups
- Report generated after every backup from an editable template
- Daily scheduling (built-in scheduler, Windows Task Scheduler, or cron)
- Restore script with safe extraction
- Dry-run mode and logging

## Tech Stack
- Python 3
- PyYAML (configuration)
- schedule (daily scheduler)
- boto3 (Amazon S3, optional)

## Project Structure
```
cloud-backup-automation/
├── scripts/
│   ├── restore.py             # restore a backup
│   ├── run_backup.bat         # run one backup (Windows)
│   ├── run_backup.sh          # run one backup (Linux / Mac)
│   ├── schedule_windows.bat   # create daily Windows task
│   └── schedule_linux.sh      # create daily cron job
├── templates/
│   └── report_template.txt    # backup report layout
├── backup.py                  # main program
├── config.yaml                # all settings
├── requirements.txt
└── README.md
```

## How to Run

1. Clone the repository
```bash
git clone https://github.com/leninanto5/cloud-backup-automation.git
cd cloud-backup-automation
```

2. Install dependencies
```bash
pip install -r requirements.txt
```

3. Open `config.yaml` and set the folders you want to back up under `sources`

4. Preview what will be backed up
```bash
python backup.py --dry-run
```

5. Run a backup
```bash
python backup.py
```

## Commands
| Command | Description |
|---|---|
| `python backup.py` | Run one backup now |
| `python backup.py --dry-run` | Show what would be backed up |
| `python backup.py --list` | List existing backups |
| `python backup.py --schedule` | Run continuously, backup daily at the time in `config.yaml` |
| `python scripts/restore.py --latest` | Restore the newest backup into `restored/` |
| `python scripts/restore.py <file.zip> --to <folder>` | Restore a specific backup |

## Configuration (`config.yaml`)
| Setting | Description |
|---|---|
| `backup_name` | Prefix used in backup file names |
| `sources` | Folders or files to back up |
| `exclude` | Names or patterns to skip |
| `destination.type` | `local` or `s3` |
| `destination.local_path` | Folder for local backups |
| `destination.s3` | Bucket, prefix and region for S3 |
| `retention.keep_last` | Number of newest backups to keep |
| `schedule.time` | Daily backup time (24-hour) |

## Using Amazon S3
1. Set `destination.type` to `s3` in `config.yaml` and fill in the bucket details
2. Configure AWS credentials on your computer (`aws configure`) or set the `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` environment variables
3. Run `python backup.py`

## Automatic Daily Backup
- **Windows:** run `scripts\schedule_windows.bat`
- **Linux / Mac:** run `sh scripts/schedule_linux.sh`
- **Any system:** run `python backup.py --schedule` and keep it running

## Author
**Leninanto**
GitHub: [leninanto5](https://github.com/leninanto5)
