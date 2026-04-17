@echo off

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.10+
    pause
    exit /b 1
)

if not exist ".venv" (
    echo [1/3] Creating virtual environment...
    python -m venv .venv
) else (
    echo [1/3] Virtual environment already exists, skipping.
)

echo [2/3] Installing dependencies...
call .venv\Scripts\activate.bat
pip install --upgrade pip -q
pip install moderngl glfw "imgui[glfw]" numpy -q

echo [3/3] Done.
echo.
echo Run:  double-click run.bat
echo   or: .venv\Scripts\python main.py [optional: path\to\file.vox]
echo.
pause
