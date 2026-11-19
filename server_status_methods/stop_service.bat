@echo off
title Stop Unified IMB & IMS Status Service
echo ====================================================
echo    STOPPING UNIFIED IMB & IMS STATUS SERVICE
echo ====================================================
echo.

:: Temukan PID yang mendengarkan di port 8088 dan matikan prosesnya
set found=0
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8088 ^| findstr LISTENING') do (
    echo Menutup proses dengan PID: %%a...
    taskkill /f /pid %%a >nul 2>&1
    set found=1
)

if %found%==1 (
    echo Servis berhasil dihentikan.
) else (
    echo Tidak ada servis yang sedang berjalan di port 8088.
)

echo.
pause
