"""
Configuration management for pwncloudos-sync.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
import yaml


@dataclass
class Config:
    """Configuration for pwncloudos-sync."""
    # Update scope
    update_all: bool = False
    category: Optional[str] = None
    tools: List[str] = field(default_factory=list)
    exclude_tools: List[str] = field(default_factory=list)

    # Behavior
    dry_run: bool = False
    force: bool = False
    no_rollback: bool = False
    no_confirm: bool = False
    parallel: bool = False
    max_workers: int = 4

    # Output
    verbose: int = 0
    quiet: bool = False
    log_file: Path = field(default_factory=lambda: Path("logs/pwncloudos-sync.log"))
    json_output: bool = False

    # Information
    list_only: bool = False
    check_only: bool = False

    # Directories
    state_dir: Path = field(default_factory=lambda: Path("state/"))
    backup_dir: Path = field(default_factory=lambda: Path("/tmp/pwncloudos-sync-backup/"))

    # Tool locations
    opt_dirs: List[Path] = field(default_factory=lambda: [
        Path("/opt/aws_tools"),
        Path("/opt/azure_tools"),
        Path("/opt/gcp_tools"),
        Path("/opt/multi_cloud_tools"),
        Path("/opt/ps_tools"),
        Path("/opt/code_scanning"),
        Path("/opt/cracking-tools"),
    ])


def load_config(args) -> Config:
    """Load configuration from arguments and config file."""
    config = Config()

    # Load from config file if exists
    config_file = Path.home() / ".config" / "pwncloudos-sync" / "config.yaml"
    if config_file.exists():
        with open(config_file) as f:
            file_config = yaml.safe_load(f)
            if file_config:
                apply_config_file(config, file_config)

    # Override with command line arguments
    apply_cli_args(config, args)

    # Ensure directories exist
    config.log_file.parent.mkdir(parents=True, exist_ok=True)
    config.state_dir.mkdir(parents=True, exist_ok=True)
    config.backup_dir.mkdir(parents=True, exist_ok=True)

    return config


def apply_config_file(config: Config, file_config: dict):
    """Apply settings from config file."""
    if 'verbose' in file_config:
        config.verbose = file_config['verbose']
    if 'parallel' in file_config:
        config.parallel = file_config['parallel']
    if 'max_workers' in file_config:
        config.max_workers = file_config['max_workers']
    if 'exclude_tools' in file_config:
        config.exclude_tools = file_config['exclude_tools']
    if 'log_file' in file_config:
        config.log_file = Path(file_config['log_file'])


def apply_cli_args(config: Config, args):
    """Apply command line arguments to config."""
    if hasattr(args, 'all') and args.all:
        config.update_all = True
    if hasattr(args, 'category') and args.category:
        config.category = args.category
        config.update_all = False
    if hasattr(args, 'tools') and args.tools:
        config.tools = args.tools
        config.update_all = False
    if hasattr(args, 'exclude_tools') and args.exclude_tools:
        config.exclude_tools.extend(args.exclude_tools)

    if hasattr(args, 'dry_run'):
        config.dry_run = args.dry_run
    if hasattr(args, 'force'):
        config.force = args.force
    if hasattr(args, 'no_rollback'):
        config.no_rollback = args.no_rollback
    if hasattr(args, 'no_confirm'):
        config.no_confirm = args.no_confirm
    if hasattr(args, 'parallel'):
        config.parallel = args.parallel
    if hasattr(args, 'workers'):
        config.max_workers = args.workers

    if hasattr(args, 'verbose'):
        config.verbose = args.verbose
    if hasattr(args, 'quiet'):
        config.quiet = args.quiet
    if hasattr(args, 'log_file') and args.log_file:
        config.log_file = args.log_file
    if hasattr(args, 'json'):
        config.json_output = args.json

    if hasattr(args, 'list_only'):
        config.list_only = args.list_only
    if hasattr(args, 'check_only'):
        config.check_only = args.check_only
