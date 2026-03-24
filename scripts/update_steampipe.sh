#!/bin/bash
# Update Steampipe
# Custom updater script for steampipe

set -e

echo "Updating Steampipe..."

# Download and run official installer (needs root for /usr/local/bin)
curl -fsSL https://raw.githubusercontent.com/turbot/steampipe/main/install.sh | sudo sh

echo "Steampipe updated successfully"
