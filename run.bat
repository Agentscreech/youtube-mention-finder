@echo off
setlocal
cd /d "%~dp0"
python youtube_mention_finder.py %*
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Script ended with an error.
)
if "%~1"=="" (
    pause
)
