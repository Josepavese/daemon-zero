#!/bin/bash
set -e

echo "=== DaemonZero Full Test Script ==="
echo "=== Step 1: Expanding Filesystem (15GB) ==="
# Expand partition 2 (usually root)
if growpart /dev/sda 2; then
    echo "Partition expanded."
else
    echo "Partition already expanded or error (ignoring if already max size)."
fi
resize2fs /dev/sda2

echo "=== Step 2: Ensuring Prerequisites ==="
sudo apt-get update
sudo apt-get install -y curl sshpass jq cloud-guest-utils


echo "=== Step 3: Installing DaemonZero ==="
# Using the install script we pushed to GitHub main branch
curl -L https://raw.githubusercontent.com/Josepavese/daemon-zero/main/daemon-zero-install.sh | bash

echo "=== Step 4: Verification ==="
echo "Waiting for DaemonZero Manager to start on port 8080..."
sleep 15
if curl -s http://localhost:8080/api/status | grep "alive"; then
    echo -e "\n[SUCCESS] Manager is ALIVE!"
else
    echo -e "\n[ERROR] Manager failed to start."
    exit 1
fi

echo "=== Test Completed Successfully ==="
echo "Access the GUI at http://<VM_IP>:8080"
