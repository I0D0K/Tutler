```bat
@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 (
    echo.
    echo Dependency installation failed. Please check the error output above.
    pause
    exit /b 1
)

python -m PyInstaller --noconfirm --clean --windowed --onedir --name Tutler ^
    --icon "tutler.ico" ^
    --add-data "tutler-logo.png;." ^
    --add-data "tutler.ico;." ^
    main.py

if errorlevel 1 (
    echo.
    echo Packaging failed. Please check the error output above.
    pause
    exit /b 1
)

echo.
echo Build complete: dist\Tutler\Tutler.exe
pause
```