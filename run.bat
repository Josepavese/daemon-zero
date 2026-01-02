@echo off
setlocal enabledelayedexpansion

echo [DaemonZero] Starting Windows Setup...

:: Check for Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Please install Python 3.10+ from python.org
    pause
    exit /b 1
)

:: Virtual Environment Setup
if not exist "manager\.venv" (
    echo [INFO] Creating virtual environment...
    python -m venv manager\.venv
)

:: Activate and Install
call manager\.venv\Scripts\activate
echo [INFO] Installing requirements...
pip install -r manager/requirements.txt

:: Launch
echo [INFO] Launching DaemonZero Manager...
python manager/dz-launcher.py

pause
