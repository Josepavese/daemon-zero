#!/bin/bash
# DaemonZero One-Line Installer
set -e

REPO_URL="https://github.com/Josepavese/daemon-zero/archive/refs/heads/test.tar.gz"
INSTALL_DIR="daemon-zero"

echo "=== DaemonZero Installer ==="

# 1. Check prerequisites
command -v curl >/dev/null 2>&1 || { echo >&2 "Required 'curl' but it's not installed. Aborting."; exit 1; }
command -v tar >/dev/null 2>&1 || { echo >&2 "Required 'tar' but it's not installed. Aborting."; exit 1; }

# 2. Download and Extract (Lightweight, no git history)
echo "[INFO] Downloading latest version..."
rm -rf "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
curl -L "$REPO_URL" | tar xz -C "$INSTALL_DIR" --strip-components=1

# 3. Setup Permissions
chmod +x "$INSTALL_DIR/run.sh"

echo "[SUCCESS] Installed in ./$INSTALL_DIR"
echo "[INFO] Starting DaemonZero..."

# 4. Run
cd "$INSTALL_DIR"
./run.sh
