#!/bin/bash

echo "🔄 Starting TMS System Update..."

# 1. Git Pull (if applicable)
if [ -d ".git" ]; then
    echo "📥 Pulling changes from Git..."
    git pull
    if [ $? -eq 0 ]; then
        echo "✅ Code updated."
    else
        echo "❌ Git pull failed. Please check your network or git status."
        exit 1
    fi
else
    echo "⚠️ No .git folder found. Assuming manual file copy."
fi

# 2. Restart Service
echo "♻️ Restarting TMS Service..."
sudo systemctl restart tms

# 3. Check Status
sleep 2
sudo systemctl status tms --no-pager

echo "---------------------------------------------------"
echo "✅ Update process finished."
echo "---------------------------------------------------"
