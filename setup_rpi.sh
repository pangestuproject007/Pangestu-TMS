#!/bin/bash

echo "🚀 Starting TMS System Setup for Raspberry Pi..."

# 1. Update System & Install Python Dependencies
echo "📦 Installing System Dependencies..."
sudo apt-get update
sudo apt-get install -y python3-pip

# 2. Python Environment
echo "🐍 Installing Python Libraries..."
# Using --break-system-packages for recent Raspberry Pi OS versions (Bookworm+)
# ideally use venv, but this ensures global availability for the service easily
pip3 install tornado pysnmp --break-system-packages 2>/dev/null || pip3 install tornado pysnmp

# 3. Create Systemd Service
echo "⚙️ Configuring Auto-Start Service..."
SERVICE_FILE="/etc/systemd/system/tms.service"
CURRENT_DIR=$(pwd)
USER_NAME=$(whoami)

# Detect python path
PY_PATH=$(which python3)

sudo bash -c "cat > $SERVICE_FILE" <<EOL
[Unit]
Description=Cinema TMS Server
After=network.target

[Service]
User=$USER_NAME
WorkingDirectory=$CURRENT_DIR
ExecStart=$PY_PATH $CURRENT_DIR/backend/server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOL

# 4. Enable Service
sudo systemctl daemon-reload
sudo systemctl enable tms
echo "✅ Service Installed. Starting..."
sudo systemctl restart tms
sleep 2
sudo systemctl status tms --no-pager

echo "---------------------------------------------------"
echo "🎉 Setup Complete!"
echo "📡 Access your TMS at: http://$(hostname -I | awk '{print $1}'):43728"
echo "---------------------------------------------------"
