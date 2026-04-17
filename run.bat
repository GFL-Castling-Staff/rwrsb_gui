@echo off

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found. Please run setup.bat first.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat
python main.py %*
echo.
echo --- Program exited (see error above if any) ---
pause
