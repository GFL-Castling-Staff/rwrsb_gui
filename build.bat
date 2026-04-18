@echo off
setlocal

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found. Please run setup.bat first.
    exit /b 1
)

call .venv\Scripts\activate.bat

if not exist ".venv\Scripts\pyinstaller.exe" (
    echo [INFO] PyInstaller not found in .venv, installing...
    pip install pyinstaller
    if errorlevel 1 (
        echo [ERROR] Failed to install PyInstaller.
        exit /b 1
    )
)

echo [1/2] Cleaning old build output...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [2/2] Building rwrsb_gui...
pyinstaller --noconfirm rwrsb_gui.spec
if errorlevel 1 (
    echo [ERROR] Build failed.
    exit /b 1
)

echo.
echo Build complete:
echo   dist\rwrsb_gui\rwrsb_gui.exe
echo.
echo Recommended release artifact:
echo   zip the whole dist\rwrsb_gui folder
echo.
endlocal
