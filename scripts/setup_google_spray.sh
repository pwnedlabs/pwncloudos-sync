#!/bin/bash
# Replace SprayShark with google-spray on PwnCloudOS
# Run ONCE on the VM to set up the new tool directory and launcher

set -e

TOOL_DIR="/opt/gcp_tools/google_spray"
OLD_DIR="/opt/gcp_tools/sprayshark"
LAUNCHER="/opt/gcp_tools/google_spray/google-spray_launcher.sh"

echo "[*] Setting up google-spray..."

# Remove old sprayshark directory if it exists
if [ -d "$OLD_DIR" ]; then
    echo "[*] Removing old sprayshark directory..."
    sudo rm -rf "$OLD_DIR"
fi

# Remove old sprayshark pipx package if installed
if command -v sprayshark &>/dev/null; then
    echo "[*] Removing sprayshark pipx package..."
    pipx uninstall sprayshark 2>/dev/null || true
fi

# Clone google-spray
if [ ! -d "$TOOL_DIR" ]; then
    echo "[*] Cloning google-spray..."
    sudo git clone https://github.com/pwnedlabs/google-spray.git "$TOOL_DIR"
    sudo chown -R root:root "$TOOL_DIR"
else
    echo "[*] google-spray directory already exists, pulling latest..."
    sudo git -C "$TOOL_DIR" pull origin main
fi

# Install dependencies
echo "[*] Installing playwright..."
sudo pip3 install playwright --break-system-packages
echo "[*] Installing chromium browser engine..."
playwright install chromium

# Create launcher script
echo "[*] Creating launcher..."
sudo tee "$LAUNCHER" > /dev/null << 'EOF'
#!/bin/bash
# google-spray launcher for PwnCloudOS
# Google Workspace Password Sprayer
# Usage: google-spray <emails.txt> <passwords.txt>

TOOL_DIR="/opt/gcp_tools/google_spray"

if [ $# -lt 2 ]; then
    echo "Usage: google-spray <emails.txt> <passwords.txt>"
    echo ""
    echo "Google Workspace Password Sprayer"
    echo "Requires: pip3 install playwright && playwright install chromium"
    exit 1
fi

cd "$TOOL_DIR"
python3 google-spray.py "$@"
EOF

sudo chmod +x "$LAUNCHER"

# Create symlink in /usr/local/bin for easy access
sudo ln -sf "$LAUNCHER" /usr/local/bin/google-spray

echo "[✓] google-spray installed successfully!"
echo "    Usage: google-spray emails.txt passwords.txt"
