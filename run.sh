#!/bin/bash
# DaemonZero Runner for Linux

echo "Starting DaemonZero Manager..."

# 1. Check for python3-venv (Common missing dependency on Debian/Ubuntu)
if ! python3 -c "import venv, ensurepip" > /dev/null 2>&1; then
    echo "[WARN] python3-venv is missing or broken. Attempting to install system prerequisites..."
    if [ -f /etc/debian_version ]; then
        # Detect specific version
        PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        echo "[INFO] Detected Python $PY_VER. Installing: sudo apt update && sudo apt install -y python3-venv python${PY_VER}-venv"
        sudo apt update || true
        sudo apt install -y python3-venv python${PY_VER}-venv
    else
        echo "[ERROR] python3-venv/ensurepip is required to create the manager's sandbox."
        echo "Please install it using your system's package manager."
        exit 1
    fi
fi

# 2. Check if .venv exists and is valid, if not create it
if [ ! -f "manager/.venv/bin/activate" ]; then
    echo "Virtual environment missing or broken. Setting up..."
    rm -rf manager/.venv
    python3 -m venv manager/.venv
    if [ ! -f "manager/.venv/bin/activate" ]; then
        echo "[ERROR] Failed to create virtual environment in manager/.venv"
        echo "Please ensure python3-venv is installed correctly."
        exit 1
    fi
fi

# Activate venv
source manager/.venv/bin/activate

# Install requirements
pip install -r manager/requirements.txt

# Detect headless environment and force CLI mode
if [ -z "$DISPLAY" ]; then
    echo "[INFO] Headless environment detected. Starting in CLI mode (web server only)."
    echo "[INFO] Access the Manager at http://0.0.0.0:8080 from your browser."
    export DZ_CLI_MODE=1
fi

# Run launcher
python manager/dz-launcher.py
