@echo off
title Unified IMB & IMS Status Service
echo ====================================================
echo    STARTING UNIFIED IMB & IMS STATUS SERVICE
echo ====================================================
echo.
python "%~dp0unified_service.py"
echo.
echo Service stopped.
pause
