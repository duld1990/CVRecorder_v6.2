@echo off
setlocal
cd /d "%~dp0"
echo Use an activated Python 3.11 x64 environment, or specify its python.exe path as argument.
set "RECORDER_PYTHON=python"
if not "%~1"=="" set "RECORDER_PYTHON=%~1"
"%RECORDER_PYTHON%" -c "import sys, struct; assert sys.version_info[:2] == (3,11) and struct.calcsize('P') == 8, 'Python 3.11 x64 required'"
if errorlevel 1 goto failed
"%RECORDER_PYTHON%" -m pip install --no-index --find-links="%~dp0wheels" --only-binary=:all: -r requirements.txt
if errorlevel 1 goto failed
"%RECORDER_PYTHON%" check_install.py
if errorlevel 1 goto failed
echo Installed. Run recorder.py with this same Python environment.
pause
exit /b 0
:failed
echo Installation failed. Check Python version and error text.
pause
exit /b 1
