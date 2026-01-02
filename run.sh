#!/bin/bash
# DaemonZero Runner for Linux

echo "Starting DaemonZero Manager..."

# 1. Check for python3-venv (Common missing dependency on Debian/Ubuntu)
if ! python3 -m venv --help > /dev/null 2>&1; then
    echo "[WARN] python3-venv is missing. Attempting to install system prerequisites..."
    if [ -f /etc/debian_version ]; then
        # On Debian/Ubuntu, try to install it. This requires sudo.
        echo "[INFO] Running: sudo apt update && sudo apt install -y python3-venv"
        sudo apt update && sudo apt install -y python3-venv
    else
        echo "[ERROR] python3-venv is required to create the manager's sandbox."
        echo "Please install it using your system's package manager."
        exit 1
    fi
fi

# 2. Check if .venv exists, if not create it
if [ ! -d "manager/.venv" ]; then
    echo "First run detected. Setting up virtual environment..."
    python3 -m venv manager/.venv
fi

# Activate venv
source manager/.venv/bin/activate

# Install requirements
pip install -r manager/requirements.txt

# Run launcher
python manager/dz-launcher.py
