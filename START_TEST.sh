#!/bin/bash
set -e
echo "=== 🚀 Inizio Test Real Code: DaemonZero ==="

# 1. Espandi il filesystem (necessario perché il disco VirtualBox è stato allargato)
echo "=== Step 1: Espansione Disco ==="
sudo apt-get update && sudo apt-get install -y cloud-guest-utils
sudo growpart /dev/sda 2 || true
sudo resize2fs /dev/sda2

# 2. Installa prerequisiti minimi
echo "=== Step 2: Prerequisiti ==="
sudo apt-get install -y curl sshpass jq

# 3. Lancio dell'installatore REALE
echo "=== Step 3: Lancio Installatore Reale ==="
curl -L https://raw.githubusercontent.com/Josepavese/daemon-zero/test/install.sh | bash

echo "✅ Test Completato! Il Manager è in esecuzione."
