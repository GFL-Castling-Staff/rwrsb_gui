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

echo [1/3] Cleaning old build output...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [2/3] Building rwrsb_gui...
pyinstaller --noconfirm rwrsb_gui.spec
if errorlevel 1 (
    echo [ERROR] rwrsb_gui build failed.
    exit /b 1
)

echo [3/3] Building rwrsb_anim...
pyinstaller --noconfirm rwrsb_anim.spec
if errorlevel 1 (
    echo [ERROR] rwrsb_anim build failed.
    exit /b 1
)

echo.
echo Build complete:
echo   dist\rwrsb_gui\rwrsb_gui.exe   (skeleton/binding editor)
echo   dist\rwrsb_anim\rwrsb_anim.exe (animation editor)
echo.
echo IMPORTANT:
echo   Run the EXE from dist\<name>\<name>.exe
echo   Do NOT run build\<name>\<name>.exe
echo.
echo Recommended release artifacts:
echo   zip dist\rwrsb_gui  and  dist\rwrsb_anim  separately
echo.
endlocal
