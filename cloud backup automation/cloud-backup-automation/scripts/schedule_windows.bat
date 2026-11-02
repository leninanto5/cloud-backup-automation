@echo off
REM Creates a Windows Task Scheduler job that runs the backup every day
set TASK_NAME=CloudBackupAutomation
set RUN_TIME=02:00

schtasks /create /tn "%TASK_NAME%" /tr "\"%~dp0run_backup.bat\"" /sc daily /st %RUN_TIME% /f

echo.
echo Task "%TASK_NAME%" will run every day at %RUN_TIME%.
echo To remove it, run: schtasks /delete /tn "%TASK_NAME%" /f
pause
