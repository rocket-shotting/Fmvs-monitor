@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [1/2] Installing packages...
python -m pip install -r requirements.txt pyinstaller || goto :error
echo [2/2] Building EXE...
python -m PyInstaller --noconfirm --clean "FMVS_Vision_Agent.spec" || goto :error
echo.
echo Done: dist\FMVS_Vision_Agent.exe
pause
exit /b 0
:error
echo Build failed.
pause
exit /b 1
