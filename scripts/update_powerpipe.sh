#!/bin/bash
# Update Powerpipe
# Custom updater script for powerpipe

set -e

echo "Updating Powerpipe..."

# Download and run official installer (needs root for /usr/local/bin)
curl -fsSL https://raw.githubusercontent.com/turbot/powerpipe/main/install.sh | sudo sh

echo "Powerpipe updated successfully"
