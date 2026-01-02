#!/bin/bash

# install.sh - Idempotent installation script for DaemonZero Environment

set -u

# Function to check command existence
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

echo "Starting DaemonZero Environment Setup..."

# 1. Docker Installation
if command_exists docker; then
    echo "[OK] Docker is already installed."
else
    echo "[INFO] Docker not found. Starting installation..."
    # Attempt to use official convenience script, or fallback to manual if preferred.
    # Using convenience script for broad compatibility on Linux.
    if curl -fsSL https://get.docker.com -o get-docker.sh; then
        sh get-docker.sh
        rm get-docker.sh
        echo "[SUCCESS] Docker installed."
    else
        echo "[ERROR] Failed to download or run Docker installation script."
        exit 1
    fi
fi

# 2. Setup User Permissions for Docker
# Check if user is already in docker group
if groups "$USER" | grep &>/dev/null "\bdocker\b"; then
    echo "[OK] User '$USER' is already in 'docker' group."
else
    echo "[INFO] Adding user '$USER' to 'docker' group..."
    if sudo usermod -aG docker "$USER"; then
        echo "[WARN] You have been added to the 'docker' group. You may need to log out and back in (or run 'newgrp docker') for changes to take effect."
    else
        echo "[ERROR] Failed to add user to docker group."
        exit 1
    fi
fi

# 3. Setup Directories
BASE_DIR="$HOME/daemon-zero"
SUBDIRS=("config" "agents" "memory" "knowledge")

if [ ! -d "$BASE_DIR" ]; then
    echo "[INFO] Creating base directory: $BASE_DIR"
    mkdir -p "$BASE_DIR"
else
    echo "[OK] Base directory exists: $BASE_DIR"
fi

for dir in "${SUBDIRS[@]}"; do
    TARGET="$BASE_DIR/$dir"
    if [ ! -d "$TARGET" ]; then
        echo "[INFO] Creating subdirectory: $TARGET"
        mkdir -p "$TARGET"
    else
        echo "[OK] Subdirectory exists: $TARGET"
    fi
done

# 4. Setup dz-manage script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANAGE_SCRIPT="$SCRIPT_DIR/dz-manage"

if [ -f "$MANAGE_SCRIPT" ]; then
    if [ -x "$MANAGE_SCRIPT" ]; then
        echo "[OK] dz-manage is already executable."
    else
        echo "[INFO] Making dz-manage executable..."
        chmod +x "$MANAGE_SCRIPT"
    fi
    
    # Ideally, symlink to somewhere in PATH, but for now just inform user
    if command_exists dz-manage; then
         echo "[OK] dz-manage is in PATH."
    else
         # Check if symlink exists in /usr/local/bin to be idempotent
         if [ -L "/usr/local/bin/dz-manage" ]; then
             echo "[OK] Symlink /usr/local/bin/dz-manage exists."
         else
             echo "[INFO] Creating symlink for dz-manage in /usr/local/bin (requires sudo)..."
             sudo ln -sf "$MANAGE_SCRIPT" /usr/local/bin/dz-manage || echo "[WARN] Failed to create symlink. You can run it via ./dz-manage"
         fi
    fi
else
    echo "[WARN] dz-manage script not found in $SCRIPT_DIR. Please ensure it is present."
fi

echo "Setup Complete!"
