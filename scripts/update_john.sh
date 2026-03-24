#!/bin/bash
# Update John the Ripper
# Custom updater script for John the Ripper (jumbo version)

set -e

JOHN_PATH="/opt/cracking-tools/john"

echo "Updating John the Ripper..."

cd "$JOHN_PATH"

# Pull latest changes (needs sudo for /opt/ paths)
sudo git -C "$JOHN_PATH" config --global --add safe.directory "$JOHN_PATH" 2>/dev/null || true
sudo git -C "$JOHN_PATH" pull origin bleeding-jumbo

# Compile
cd src
sudo ./configure
sudo make -s clean
sudo make -sj$(nproc)

echo "John the Ripper updated successfully"
