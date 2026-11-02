#!/bin/sh
# Adds a cron job that runs the backup every day at 02:00 (Linux / Mac)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LINE="0 2 * * * /bin/sh $SCRIPT_DIR/run_backup.sh"

( crontab -l 2>/dev/null | grep -v "run_backup.sh"; echo "$LINE" ) | crontab -
echo "Cron job added: $LINE"
