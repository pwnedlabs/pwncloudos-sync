"""
Base updater class for pwncloudos-sync.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
from pathlib import Path
import logging

logger = logging.getLogger('pwncloudos-sync')


@dataclass
class UpdateResult:
    """Result of an update operation."""
    success: bool
    tool_name: str
    old_version: Optional[str] = None
    new_version: Optional[str] = None
    error_message: Optional[str] = None
    duration_seconds: float = 0.0
    skipped: bool = False
    skip_reason: Optional[str] = None


class BaseUpdater(ABC):
    """Abstract base class for tool updaters."""

    def __init__(self, tool, config):
        """
        Initialize the updater.

        Args:
            tool: Tool object
            config: Configuration object
        """
        self.tool = tool
        self.config = config
        self.logger = logging.getLogger(f'pwncloudos-sync.{tool.name}')

    @abstractmethod
    def get_current_version(self) -> Optional[str]:
        """
        Get currently installed version.

        Returns:
            Version string or None if unknown
        """
        pass

    @abstractmethod
    def get_latest_version(self) -> Optional[str]:
        """
        Get latest available version from source.

        Returns:
            Version string or None if unknown
        """
        pass

    @abstractmethod
    def needs_update(self) -> bool:
        """
        Check if update is needed.

        Returns:
            True if update is available
        """
        pass

    @abstractmethod
    def perform_update(self) -> UpdateResult:
        """
        Execute the update.

        Returns:
            UpdateResult with success/failure info
        """
        pass

    def verify_update(self) -> bool:
        """
        Verify update succeeded.

        Returns:
            True if verification passed
        """
        # Default implementation - can be overridden
        if self.tool.version_command:
            import shlex
            import subprocess
            try:
                result = subprocess.run(
                    shlex.split(self.tool.version_command),
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                return result.returncode == 0
            except Exception:
                return False
        return True

    def create_backup(self):
        """Create backup before update (handled by RollbackEngine)."""
        pass

    def rollback(self) -> bool:
        """
        Restore from backup (handled by RollbackEngine).

        Returns:
            True if rollback succeeded
        """
        return True
