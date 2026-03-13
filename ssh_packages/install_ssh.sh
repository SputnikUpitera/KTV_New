#!/bin/bash
set -e

echo "=== Installing OpenSSH Server (offline) ==="

cd "$(dirname "$0")"

if systemctl is-active --quiet ssh 2>/dev/null || systemctl is-active --quiet sshd 2>/dev/null; then
    echo "SSH server is already running. Nothing to do."
    exit 0
fi

echo "[1/3] Installing packages..."
sudo dpkg -i openssh-client_8.2p1-4ubuntu0.13_amd64.deb 2>/dev/null || true
sudo dpkg -i openssh-sftp-server_8.2p1-4ubuntu0.13_amd64.deb 2>/dev/null || true
sudo dpkg -i openssh-server_8.2p1-4ubuntu0.13_amd64.deb

echo "[2/3] Enabling SSH service..."
sudo systemctl enable ssh
sudo systemctl start ssh

echo "[3/3] Verifying..."
if systemctl is-active --quiet ssh; then
    echo ""
    echo "SSH server is running!"
    IP=$(hostname -I | awk '{print $1}')
    echo "IP address: $IP"
    echo "Now you can connect from OperatorKTV GUI."
else
    echo "ERROR: SSH failed to start. Check: sudo journalctl -u ssh -n 20"
    exit 1
fi
