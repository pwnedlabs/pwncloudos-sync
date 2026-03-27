# pwncloudos-sync

A standalone tool that performs in-place upgrades of all security tools installed on [PwnCloudOS](https://pwncloudos.pwnedlabs.io/) without requiring users to download fresh OS images.

## Features

- **Smart version detection**: Checks installed vs latest version for 44 security tools
- **Interactive default mode**: Shows a color-coded version table, then offers to update
- **Auto-retry**: Failed tools are automatically retried after the first pass
- **Multi-method updates**: Supports git, pipx, binary downloads, Docker, apt, custom scripts
- **Architecture-aware**: Automatically detects AMD64/ARM64 and downloads correct binaries
- **Non-destructive**: Full rollback on any failure — never breaks a working tool
- **Launcher-safe**: Never modifies PwnCloudOS launcher scripts or desktop files
- **Category colors**: Each tool category (AWS, Azure, GCP, etc.) gets a distinct color

## Quick Start

```bash
# On your PwnCloudOS VM:
cd /opt/pwncloudos-sync

# Install dependencies (first time only)
pip3 install -r requirements.txt --break-system-packages

# Run the updater (default: check + offer to update)
python3 -m src.main
```

## Usage

```bash
# Default mode — check all tools, show table, offer to update
python3 -m src.main

# Update all tools (skip the check table, go straight to updating)
python3 -m src.main --all

# Update all tools, skip confirmation prompt
python3 -m src.main --all -y

# Check for updates only (no changes)
python3 -m src.main --check

# List all tools with installed versions
python3 -m src.main --list

# Update only a specific category
python3 -m src.main --category aws
python3 -m src.main --category azure
python3 -m src.main --category gcp

# Update specific tool(s)
python3 -m src.main --tool cloudfox
python3 -m src.main --tool cloudfox --tool prowler

# Exclude tools from update
python3 -m src.main --all --exclude bloodhound

# Dry run (show what would be updated, no changes)
python3 -m src.main --dry-run

# Force update even if already at latest version
python3 -m src.main --all --force

# Verbose output (for debugging)
python3 -m src.main --all -v      # info level
python3 -m src.main --all -vv     # debug level

# Skip confirmation prompt
python3 -m src.main --all --yes
```

## Supported Tool Categories (44 tools)

| Category | Location | Example Tools |
|----------|----------|---------------|
| **aws** | `/opt/aws_tools/` | AWeSomeUserFinder, pacu, pmapper, s3-account-search |
| **azure** | `/opt/azure_tools/` | AzureHound, BloodHound, ROADtools, o365spray |
| **gcp** | `/opt/gcp_tools/` | gcp_scanner, google-spray, google-workspace-enum |
| **multi_cloud** | `/opt/multi_cloud_tools/` | cloudfox, prowler, ScoutSuite, steampipe, powerpipe |
| **ps_tools** | `/opt/ps_tools/` | AADInternals, GraphRunner, TokenTacticsV2, MFASweep |
| **code_scanning** | `/opt/code_scanning/` | trufflehog, git-secrets |
| **cracking** | `/opt/cracking-tools/` | John the Ripper, hashcat |
| **system** | system-wide | azure-cli, impacket, awscli |

## Update Methods

| Method | Description |
|--------|-------------|
| `git` / `git_python` | `git pull` with launcher file protection |
| `pipx` | `pipx upgrade` for pipx-installed tools |
| `binary` | Download arch-specific binary from GitHub Releases |
| `apt` | `apt-get upgrade` for system packages |
| `docker` | `docker compose pull` for containerized tools |
| `custom` | Run shell scripts (powerpipe, steampipe, john) |
| `file_replacement` | Download only `.py` + `requirements.txt` (lightweight) |

## Architecture Support

- **AMD64** (x86_64): VirtualBox, VMware Workstation, cloud VMs
- **ARM64** (aarch64): VMware Fusion on Apple Silicon (M-series)

## Safety Features

1. **Protected launcher files**: Backed up before git operations, restored after
2. **Automatic rollback**: Failed updates are rolled back via git reset or file restore
3. **sudo-aware**: Handles root-owned `/opt/` paths transparently
4. **safe.directory**: Auto-configures git for repos owned by root
5. **Verification**: Tools are tested after update to ensure they still work
6. **Auto-retry**: Failed tools get a second attempt after all others complete

## Requirements

- Python 3.10+ (Python 3.11 on Debian 12)
- PwnCloudOS (Debian 12 Bookworm)
- Internet connectivity
- sudo access (for `/opt/` directory writes)
- PyYAML, requests, packaging (`pip3 install -r requirements.txt`)

## Configuration

Configuration file location: `~/.config/pwncloudos-sync/config.yaml`

```yaml
# Example configuration
verbose: true
parallel: true
max_workers: 4
skip_tools:
  - bloodhound  # Skip Docker-based tools
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All updates successful (or all up-to-date) |
| 1 | Some updates failed (partial success) |
| 2 | All updates failed |
| 4 | Network connectivity error |
| 5 | sudo access denied |

## One-Time Setup (google-spray)

To replace SprayShark with google-spray:

```bash
sudo bash /opt/pwncloudos-sync/scripts/setup_google_spray.sh
```

## Contributing

Contributions are welcome!

## Contributors

All contributors are acknowledged on the [PwnCloudOS website](https://pwncloudos.pwnedlabs.io/) and in the repository README.

## License

MIT License — see [LICENSE](LICENSE) for details.

## Credits

- [PwnCloudOS](https://pwncloudos.pwnedlabs.io/) by [PwnedLabs](https://pwnedlabs.io/)
- All the amazing security tool authors

## Links

- [PwnCloudOS Download](https://pwncloudos.pwnedlabs.io/)
- [PwnCloudOS Documentation](https://pwncloudos.readthedocs.io/)
- [GitHub Repository](https://github.com/pwnedlabs/pwncloudos-sync)
