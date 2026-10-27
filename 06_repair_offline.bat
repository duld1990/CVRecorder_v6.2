@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0manage_environment.ps1" -Action Repair
set "RECORDER_RESULT=%ERRORLEVEL%"
pause
exit /b %RECORDER_RESULT%
