@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [1/2] Installing packages...
python -m pip install -r requirements.txt pyinstaller || goto :error
echo [2/2] Building EXE...
python -m PyInstaller --noconfirm --clean "NVR_흑변_검출기.spec" || goto :error
echo.
echo Done: dist\NVR_흑변_검출기.exe
pause
exit /b 0
:error
echo Build failed.
pause
exit /b 1
