@echo off
echo ========================================================
echo   PROJECTOR MONITORING - DEPLOY TO RASPBERRY PI
echo ========================================================
echo.
echo Target: pangestutms@192.168.0.155
echo.

:: 1. Copy Files (Excluding .git if exists)
echo [1/2] Copying files to Raspberry Pi...
scp -o StrictHostKeyChecking=no -r "d:\Projector Monitoring\*" pangestutms@192.168.0.155:/home/pangestutms/projector-monitoring/

:: 2. Restart Service
echo.
echo [2/2] Restarting TMS Service...
ssh -o StrictHostKeyChecking=no pangestutms@192.168.0.155 "sudo systemctl restart tms"

echo.
echo ========================================================
echo   DEPLOYMENT COMPLETE!
echo ========================================================
echo.
pause
