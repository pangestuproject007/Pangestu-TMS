@echo off
title PangestuTMS - START SERVER
color 0a

echo ==========================================
echo       PangestuTMS - START SERVER
echo ==========================================
echo.

:: Set Python Path
set PYTHONPATH=%CD%\backend

echo [1/1] Menjalankan server di port 5050...
echo Dashboard: http://localhost:5050
echo.
echo JANGAN TUTUP JENDELA INI SELAMA SERVER BERJALAN
echo.

python backend/server.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Gagal menjalankan server. 
    echo Pastikan tidak ada server lain yang sedang berjalan.
    pause
)
