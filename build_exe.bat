@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo.
echo Installing dependencies...
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 (
  echo.
  echo Dependency installation failed. Please check the error output above.
  pause
  exit /b 1
)

echo.
echo Cleaning previous build...
if exist build rmdir /s /q build
if exist dist\Tutler rmdir /s /q dist\Tutler
if exist Tutler.spec del /q Tutler.spec

echo.
echo Building Tutler...

python -m PyInstaller --noconfirm --clean --windowed --name Tutler ^
  --icon tutler.ico ^
  --add-data "tutler-logo.png;." ^
  --add-data "tutler.ico;." ^
  --exclude-module tensorflow ^
  --exclude-module keras ^
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