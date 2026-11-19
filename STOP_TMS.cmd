@echo off
title PangestuTMS - STOP SERVER
color 0c

echo ==========================================
echo       PangestuTMS - STOP SERVER
echo ==========================================
echo.

echo [1/1] Mematikan semua proses Python (TMS)...
taskkill /F /IM python.exe /T

echo.
echo SEMUA SERVER TELAH DIMATIKAN.
echo.
timeout /t 3
