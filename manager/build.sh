#!/bin/bash

# Ensure we are in a virtual environment
if [ ! -d ".venv" ]; then
    echo "[INFO] Creating virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate
pip install flask pyinstaller

echo "[INFO] Building DaemonZero Manager executable..."
pyinstaller --onefile \
            --add-data "templates:templates" \
            --add-data "install.sh:." \
            --name "daemon-zero-manager" \
            dz-launcher.py

echo "[SUCCESS] Executable created at dist/daemon-zero-manager"
