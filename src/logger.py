"""
Logging infrastructure for pwncloudos-sync.
"""

import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import List


class ColorFormatter(logging.Formatter):
    """Colored log formatter for console output."""

    COLORS = {
        'DEBUG': '\033[0;37m',     # White
        'INFO': '\033[0;32m',      # Green
        'WARNING': '\033[0;33m',   # Yellow
        'ERROR': '\033[0;31m',     # Red
        'CRITICAL': '\033[1;31m',  # Bold Red
    }
    RESET = '\033[0m'

    def format(self, record):
        color = self.COLORS.get(record.levelname, self.RESET)
        record.levelname = f"{color}{record.levelname}{self.RESET}"
        return super().format(record)


def setup_logging(config) -> logging.Logger:
    """Setup logging infrastructure."""
    logger = logging.getLogger('pwncloudos-sync')
    logger.setLevel(logging.DEBUG)

    # Clear existing handlers
    logger.handlers = []

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(ColorFormatter('%(levelname)s: %(message)s'))

    if config.quiet:
        console_handler.setLevel(logging.ERROR)
    elif config.verbose >= 2:
        console_handler.setLevel(logging.DEBUG)
    elif config.verbose >= 1:
        console_handler.setLevel(logging.INFO)
    else:
        console_handler.setLevel(logging.WARNING)

    logger.addHandler(console_handler)

    # File handler
    config.log_file.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(config.log_file)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s'
    ))
    file_handler.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)

    return logger


class SyncLogger:
    """High-level logger for sync operations."""

    SYMBOLS = {
        'updating': '\033[0;33m⟳\033[0m',  # Yellow
        'success': '\033[0;32m✓\033[0m',   # Green
        'failed': '\033[0;31m✗\033[0m',    # Red
        'skipped': '\033[0;37m○\033[0m',   # Gray
    }

    def __init__(self, log_file: Path, verbose: int = 0):
        self.log_file = log_file
        self.verbose = verbose
        self.logger = logging.getLogger('pwncloudos-sync')

    def tool_start(self, tool_name: str):
        """Log start of tool update."""
        self.logger.info(f"Updating {tool_name}...")
        print(f"{self.SYMBOLS['updating']} {tool_name}...", end='', flush=True)

    def tool_success(self, tool_name: str, old_ver: str, new_ver: str):
        """Log successful update."""
        self.logger.info(f"Updated {tool_name}: {old_ver} -> {new_ver}")
        print(f"\r  {self.SYMBOLS['success']} {tool_name}: {old_ver} -> {new_ver}")

    def tool_skip(self, tool_name: str, reason: str):
        """Log skipped tool."""
        self.logger.debug(f"Skipped {tool_name}: {reason}")
        print(f"\r  {self.SYMBOLS['skipped']} {tool_name}: {reason}")

    def tool_fail(self, tool_name: str, error: str):
        """Log failed update."""
        self.logger.error(f"Failed {tool_name}: {error}")
        print(f"\r  {self.SYMBOLS['failed']} {tool_name}: {error}")

    def summary(self, results: List):
        """Log final summary."""
        success = sum(1 for r in results if r.success and not r.skipped)
        skipped = sum(1 for r in results if r.skipped)
        failed = sum(1 for r in results if not r.success and not r.skipped)

        print("\n" + "=" * 50)
        print("Update Complete")
        print(f"  {self.SYMBOLS['success']} Updated:  {success}")
        print(f"  {self.SYMBOLS['skipped']} Skipped:  {skipped}")
        print(f"  {self.SYMBOLS['failed']} Failed:   {failed}")
        print("=" * 50)

        self.logger.info(f"Summary: {success} updated, {skipped} skipped, {failed} failed")
