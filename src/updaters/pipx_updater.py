"""
pipx package updater for pwncloudos-sync.
"""

import json
import shutil
import subprocess
from pathlib import Path
from typing import Optional
import requests
from .base import BaseUpdater, UpdateResult


class PipxUpdater(BaseUpdater):
    """Updater for pipx-installed packages."""

    def get_current_version(self) -> Optional[str]:
        """Get current version from pipx."""
        try:
            result = subprocess.run(
                ['pipx', 'list', '--json'],
                capture_output=True, text=True
            )

            if result.returncode == 0:
                data = json.loads(result.stdout)
                venv = data.get('venvs', {}).get(self.tool.pypi_name, {})
                return venv.get('metadata', {}).get('main_package', {}).get('version')
        except Exception as e:
            self.logger.debug(f"Failed to get current version: {e}")
        return None

    def get_latest_version(self) -> Optional[str]:
        """Get latest version from PyPI."""
        try:
            url = f"https://pypi.org/pypi/{self.tool.pypi_name}/json"
            response = requests.get(url, timeout=10)

            if response.ok:
                data = response.json()
                return data.get('info', {}).get('version')
        except Exception as e:
            self.logger.debug(f"Failed to get latest version: {e}")
        return None

    def needs_update(self) -> bool:
        """Check if newer version is available."""
        current = self.get_current_version()
        latest = self.get_latest_version()

        if not current or not latest:
            return True

        try:
            return self._version_key(current) < self._version_key(latest)
        except Exception:
            return current != latest

    def _version_key(self, value: str):
        """Build a sortable key from a semantic-ish version string."""
        import re

        parts = re.findall(r'\d+', value)
        return tuple(int(p) for p in parts) if parts else (0,)

    def perform_update(self) -> UpdateResult:
        """Execute pipx upgrade."""
        old_version = self.get_current_version()

        try:
            result = subprocess.run(
                ['pipx', 'upgrade', self.tool.pypi_name],
                capture_output=True, text=True, timeout=600
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
                # Check if already up to date
                if "already" in result.stdout.lower() and "up to date" in result.stdout.lower():
                    return UpdateResult(
                        success=True,
                        tool_name=self.tool.name,
                        old_version=old_version,
                        new_version=old_version,
                        skipped=True,
                        skip_reason="Already up to date"
                    )

                return UpdateResult(
                    success=False,
                    tool_name=self.tool.name,
                    old_version=old_version,
                    error_message=result.stderr or result.stdout,
                )

        except subprocess.TimeoutExpired:
            return UpdateResult(
                success=False,
                tool_name=self.tool.name,
                old_version=old_version,
                error_message="pipx upgrade timed out",
            )
        except Exception as e:
            return UpdateResult(
                success=False,
                tool_name=self.tool.name,
                old_version=old_version,
                error_message=str(e),
            )

    def verify_update(self) -> bool:
        """Verify pipx package is working."""
        if self.tool.version_command:
            try:
                result = subprocess.run(
                    self.tool.version_command.split(),
                    capture_output=True, timeout=10
                )
                # Some tools print version/help and exit non-zero; treat output as a sign of life.
                if result.returncode == 0 or result.stdout or result.stderr:
                    return True
            except Exception:
                pass

        # Prefer pipx JSON metadata and app paths for reliable verification.
        try:
            result = subprocess.run(
                ['pipx', 'list', '--json'],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                venvs = data.get('venvs', {})

                if self.tool.pypi_name and self.tool.pypi_name in venvs:
                    return True

                target_path = str(self.tool.path.resolve())
                for _pkg, pkg_info in venvs.items():
                    app_paths = pkg_info.get('metadata', {}).get('main_package', {}).get('app_paths', [])
                    if any(Path(app).expanduser().resolve().as_posix() == target_path for app in app_paths):
                        return True
        except Exception:
            pass

        # Final fallback: executable exists on PATH.
        if shutil.which(self.tool.path.name):
            return True

        return False
