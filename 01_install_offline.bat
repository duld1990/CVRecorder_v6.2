@echo off
setlocal
cd /d "%~dp0"
echo Four-channel USB Webcam - offline setup for Windows x64
if not exist "runtime\python.exe" (
 echo Installing bundled Python. Please wait...
 start "" /wait "%~dp0python-3.11.9-amd64.exe" /quiet InstallAllUsers=0 TargetDir="%~dp0runtime" Include_launcher=0 InstallLauncherAllUsers=0 Include_pip=1 Include_tcltk=1 Include_test=0 Include_doc=0 Include_dev=0 PrependPath=0 AssociateFiles=0 Shortcuts=0
 if errorlevel 1 goto failed
)
if not exist "runtime\python.exe" goto failed
"runtime\python.exe" -m pip install --no-index --find-links="%~dp0wheels" --only-binary=:all: -r requirements.txt
if errorlevel 1 goto failed
"runtime\python.exe" check_install.py
if errorlevel 1 goto failed
echo.
echo Setup complete. Run 02_start_recorder.bat to record.
pause
exit /b 0
:failed
echo.
echo SETUP FAILED. See messages above.
echo If cv2 reports DLL load failure, install vc_redist.x64.exe and retry.
echo If a newer Python 3.11 installation blocks setup, see README_Chinese.txt.
pause
exit /b 1
