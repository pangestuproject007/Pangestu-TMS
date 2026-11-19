@echo off
title Cinema Suite TMS Server
echo Starting Cinema Suite TMS Server...
echo Directory: %~dp0
cd /d "%~dp0"
python backend/server.py
if %ERRORLEVEL% neq 0 (
    echo.
    echo Server stopped with error code %ERRORLEVEL%
    pause
)
