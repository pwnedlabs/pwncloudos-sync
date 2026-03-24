"""
pipx package updater for pwncloudos-sync.
"""

import json
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Optional

import requests

from .base import BaseUpdater, UpdateResult


class PipxUpdater(BaseUpdater):
    """Updater for pipx-installed packages."""

    def _load_pipx_venvs(self) -> Dict[str, dict]:
        """Return pipx metadata keyed by package name."""
        try:
            result = subprocess.run(
                ['pipx', 'list', '--json'],
                capture_output=True,
                text=True,
                timeout=20,
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                return data.get('venvs', {})
        except Exception as e:
            self.logger.debug(f"Failed to load pipx metadata: {e}")

        return {}

    def _tool_command_name(self) -> str:
        """Best-effort command name for this tool."""
        if self.tool.version_command:
            return self.tool.version_command.split()[0]

        candidate = Path(self.tool.path).name
        if candidate and candidate != 'bin':
            return candidate

        return self.tool.name

    def _resolve_target_path(self) -> str:
        """Resolve configured tool path for path-based matching."""
        try:
            return Path(self.tool.path).expanduser().resolve(strict=False).as_posix()
        except Exception:
            return ""

    def _resolve_installed_package_name(self, venvs: Optional[Dict[str, dict]] = None) -> Optional[str]:
        """
        Resolve the installed pipx package that provides this tool.

        This allows manifest entries like pmapper/principalmapper or tools whose
        executable name differs from their pipx package name.
        """
        venvs = venvs or self._load_pipx_venvs()

        if self.tool.pypi_name and self.tool.pypi_name in venvs:
            return self.tool.pypi_name

        target_path = self._resolve_target_path()
        command_name = self._tool_command_name()

        for pkg_name, pkg_info in venvs.items():
            metadata = pkg_info.get('metadata', {})
            main_package = metadata.get('main_package', {})

            app_paths = list(main_package.get('app_paths', []))
            app_names = set(main_package.get('apps', []))

            for injected in metadata.get('injected_packages', {}).values():
                if isinstance(injected, dict):
                    app_paths.extend(injected.get('app_paths', []))
                    app_names.update(injected.get('apps', []))

            if command_name and command_name in app_names:
                return pkg_name

            if target_path:
                for app in app_paths:
                    try:
                        resolved = Path(app).expanduser().resolve(strict=False).as_posix()
                        if resolved == target_path:
                            return pkg_name
                    except Exception:
                        continue

        return None

    def get_current_version(self) -> Optional[str]:
        """Get current version from pipx."""
        try:
            venvs = self._load_pipx_venvs()
            package_name = self._resolve_installed_package_name(venvs)
            if not package_name:
                return None

            venv = venvs.get(package_name, {})
            return venv.get('metadata', {}).get('main_package', {}).get('version')
        except Exception as e:
            self.logger.debug(f"Failed to get current version: {e}")

        return None

    def get_latest_version(self) -> Optional[str]:
        """Get latest version from PyPI."""
        package = self.tool.pypi_name or self.tool.name
        try:
            url = f"https://pypi.org/pypi/{package}/json"
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

    def _tool_exists_but_not_pipx_managed(self) -> bool:
        """Return True when the tool command exists but pipx has no owning package."""
        path = Path(self.tool.path).expanduser()
        command_name = self._tool_command_name()

        if path.exists() and path.is_file():
            return True

        return bool(command_name and shutil.which(command_name))

    def perform_update(self) -> UpdateResult:
        """Execute pipx upgrade (or install if package is missing)."""
        old_version = self.get_current_version()
        venvs = self._load_pipx_venvs()
        package_name = self._resolve_installed_package_name(venvs)
        package_to_manage = package_name or self.tool.pypi_name or self.tool.name

        try:
            if not package_name and self._tool_exists_but_not_pipx_managed():
                return UpdateResult(
                    success=True,
                    tool_name=self.tool.name,
                    old_version=old_version,
                    new_version=old_version,
                    skipped=True,
                    skip_reason=(
                        f"Tool exists but is not managed by pipx ({self._tool_command_name()}); "
                        "skipping pipx update"
                    ),
                )

            command = ['pipx', 'upgrade', package_to_manage] if package_name else ['pipx', 'install', package_to_manage]
            result = subprocess.run(
                command,
                capture_output=True, text=True, timeout=600
            )

            if result.returncode == 0:
                new_version = self.get_current_version()

                return UpdateResult(
                    success=True,
                    tool_name=self.tool.name,
                    old_version=old_version,
                    new_version=new_version or old_version,
                )

            output = (result.stdout or "") + "\n" + (result.stderr or "")
            output_lower = output.lower()

            # Check if already up to date
            if "already" in output_lower and "up to date" in output_lower:
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
                error_message=output.strip() or "pipx command failed",
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
                    shlex.split(self.tool.version_command),
                    capture_output=True, timeout=10
                )
                # Some tools print version/help and exit non-zero; treat output as a sign of life.
                if result.returncode == 0 or result.stdout or result.stderr:
                    return True
            except Exception:
                pass

        # Prefer pipx JSON metadata and app paths for reliable verification.
        try:
            venvs = self._load_pipx_venvs()
            package_name = self._resolve_installed_package_name(venvs)
            if package_name:
                return True
        except Exception:
            pass

        path = Path(self.tool.path).expanduser()
        if path.exists() and path.is_file():
            return True

        # Final fallback: executable exists on PATH.
        if shutil.which(self._tool_command_name()):
            return True

        return False
