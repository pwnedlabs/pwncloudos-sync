"""
APT package updater for pwncloudos-sync.
"""

import subprocess
from typing import Optional
from .base import BaseUpdater, UpdateResult


class AptUpdater(BaseUpdater):
    """Updater for APT packages."""

    def get_current_version(self) -> Optional[str]:
        """Get current version from dpkg."""
        try:
            result = subprocess.run(
                ['dpkg', '-s', self.tool.apt_package],
                capture_output=True, text=True
            )

            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if line.startswith('Version:'):
                        return line.split(':', 1)[1].strip()
        except Exception as e:
            self.logger.debug(f"Failed to get current version: {e}")
        return None

    def get_latest_version(self) -> Optional[str]:
        """Get latest version from apt-cache."""
        try:
            result = subprocess.run(
                ['apt-cache', 'policy', self.tool.apt_package],
                capture_output=True, text=True
            )

            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'Candidate:' in line:
                        return line.split(':', 1)[1].strip()
        except Exception as e:
            self.logger.debug(f"Failed to get latest version: {e}")
        return None

    def needs_update(self) -> bool:
        """Check if newer version is available."""
        try:
            result = subprocess.run(
                ['apt', 'list', '--upgradable'],
                capture_output=True, text=True
            )

            if result.returncode == 0:
                return self.tool.apt_package in result.stdout
        except Exception:
            pass

        # Fallback to version comparison
        current = self.get_current_version()
        latest = self.get_latest_version()

        if not current or not latest:
            return False

        return current != latest

    def perform_update(self) -> UpdateResult:
        """Execute apt upgrade."""
        old_version = self.get_current_version()

        try:
            # Update package list first
            result = subprocess.run(
                ['sudo', 'apt-get', 'update'],
                capture_output=True, text=True, timeout=120
            )

            # Upgrade the specific package
            result = subprocess.run(
                ['sudo', 'apt-get', 'install', '--only-upgrade', '-y', self.tool.apt_package],
                capture_output=True, text=True, timeout=300
            )

            if result.returncode == 0:
                new_version = self.get_current_version()
                return UpdateResult(
                    success=True,
                    tool_name=self.tool.name,
                    old_version=old_version,
                    new_version=new_version,
                )
            else:
                return UpdateResult(
                    success=False,
                    tool_name=self.tool.name,
                    old_version=old_version,
                    error_message=result.stderr,
                )

        except subprocess.TimeoutExpired:
            return UpdateResult(
                success=False,
                tool_name=self.tool.name,
                old_version=old_version,
                error_message="apt upgrade timed out",
            )
        except Exception as e:
            return UpdateResult(
                success=False,
                tool_name=self.tool.name,
                old_version=old_version,
                error_message=str(e),
            )
