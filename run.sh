#!/bin/bash
# DaemonZero Quick Launch Script

# Navigate to manager directory
cd "$(dirname "$0")/manager"

# Check if virtual environment exists, if not, it's the first run
if [ ! -d ".venv" ]; then
    echo "First run detected. Setting up virtual environment..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install --upgrade pip
    pip install -r ../requirements.txt
else
    source .venv/bin/activate
fi

# Launch the manager
python dz-launcher.py
