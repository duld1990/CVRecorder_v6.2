@echo off
setlocal
cd /d "%~dp0"
if not exist "runtime\python.exe" (
 echo Bundled runtime not found. For first installation, use 01_install_offline.bat.
 echo For an existing custom Python environment, use 03_install_into_existing_python.bat.
 pause
 exit /b 1
)
"runtime\python.exe" -m pip install --no-index --find-links="%~dp0wheels" --only-binary=:all: -r requirements.txt
if errorlevel 1 goto failed
"runtime\python.exe" check_install.py
if errorlevel 1 goto failed
echo Update complete. Run 02_start_recorder.bat.
pause
exit /b 0
:failed
echo Update failed. Read the error above.
pause
exit /b 1
