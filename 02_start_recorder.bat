@echo off
setlocal
cd /d "%~dp0"
if not exist "runtime\python.exe" (
 echo First run 01_install_offline.bat.
 pause
 exit /b 1
)
"runtime\python.exe" recorder.py
if errorlevel 1 (
 echo Recorder exited with an error. Read the messages above.
 pause
)
