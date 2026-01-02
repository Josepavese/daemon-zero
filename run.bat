@echo off
TITLE DaemonZero Manager Launcher

cd /d "%~dp0\manager"

if not exist ".venv" (
    echo First run detected. Setting up virtual environment...
    python -m venv .venv
    call .venv\Scripts\activate
    python -m pip install --upgrade pip
    pip install -r ..\requirements.txt
) else (
    call .venv\Scripts\activate
)

python dz-launcher.py
pause
