@echo off
title Shuriken - Build Executable
echo.
echo  ================================================
echo   Shuriken - Build Single-Folder Executable
echo  ================================================
echo.

cd /d "%~dp0"

:: -- Step 1: Install PyInstaller if missing --
echo [1/4] Checking PyInstaller...
python -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo       Installing PyInstaller...
    pip install pyinstaller
)

:: -- Step 2: Clean previous build --
echo [2/4] Cleaning previous build...
if exist "dist\Shuriken" rmdir /s /q "dist\Shuriken"
if exist "build" rmdir /s /q "build"
if exist "Shuriken.spec" del "Shuriken.spec"

:: -- Step 3: Clean reports and caches from servers --
echo [3/4] Cleaning server caches...
for /d /r "servers" %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d"
del /q "servers\menu_delta_analyzer\reports\*.xlsx" 2>nul
del /q "servers\menu_mapping_validator\Reports\*.xlsx" 2>nul

:: -- Step 4: Build with PyInstaller --
echo [4/4] Building executable...
echo.
python -m PyInstaller ^
    --noconfirm ^
    --name Shuriken ^
    --windowed ^
    --onedir ^
    --add-data "app;app" ^
    --add-data "servers\menu_delta_analyzer;servers\menu_delta_analyzer" ^
    --add-data "servers\menu_mapping_validator;servers\menu_mapping_validator" ^
    --hidden-import "app" ^
    --hidden-import "app.main" ^
    --hidden-import "app.config" ^
    --hidden-import "app.helpers" ^
    --hidden-import "app.views" ^
    --hidden-import "app.views.otp" ^
    --hidden-import "app.views.menu_delta" ^
    --hidden-import "app.views.unmapped" ^
    --hidden-import "app.views.find_unmapped" ^
    shuriken.py

if errorlevel 1 (
    echo.
    echo  !! BUILD FAILED !!
    echo  Check the output above for errors.
    pause
    exit /b 1
)

:: -- Step 5: ZIP the output folder --
echo.
echo [5/5] Creating Shuriken.zip ...
if exist "dist\Shuriken.zip" del "dist\Shuriken.zip"
powershell -NoProfile -Command "Compress-Archive -Path 'dist\Shuriken\*' -DestinationPath 'dist\Shuriken.zip' -Force"

echo.
echo  ================================================
echo   BUILD COMPLETE
echo  ================================================
echo.
echo  EXE folder : dist\Shuriken\Shuriken.exe
echo  ZIP file   : dist\Shuriken.zip
echo.
echo  To share:
echo    1. Send dist\Shuriken.zip to your team
echo    2. They extract and double-click Shuriken.exe
echo.
echo  NOTE: Recipients still need Python + deps
echo  installed for the Menu Delta and Menu Mapping
echo  server tools (they launch Flask servers).
echo  OTP and Unmapped Checker work standalone.
echo.
pause