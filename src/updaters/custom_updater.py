"""
Custom script updater for pwncloudos-sync.
"""

import os
import shlex
import subprocess
from pathlib import Path
from typing import Optional
from .base import BaseUpdater, UpdateResult
from ..core.arch import detect_architecture


class CustomUpdater(BaseUpdater):
    """Updater that runs custom scripts."""

    def __init__(self, tool, config):
        super().__init__(tool, config)
        self.script_path = self._find_script()

    def _find_script(self) -> Optional[Path]:
        """Find the custom update script. Only accepts plain filenames (no path traversal)."""
        if self.tool.custom_handler:
            # Security: strip any directory components to prevent path traversal
            safe_name = os.path.basename(self.tool.custom_handler)
            scripts_dir = Path(__file__).parent.parent.parent / 'scripts'
            script = scripts_dir / safe_name
            if script.exists():
                return script

        return None

    def get_current_version(self) -> Optional[str]:
        """Get current version from version command."""
        if self.tool.version_command:
            try:
                result = subprocess.run(
                    shlex.split(self.tool.version_command),
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    import re
                    match = re.search(r'v?(\d+\.\d+\.?\d*)', result.stdout)
                    if match:
                        return match.group(1)
            except Exception:
                pass
        return None

    def get_latest_version(self) -> Optional[str]:
        """Get latest version (not always possible for custom tools)."""
        return None

    def needs_update(self) -> bool:
        """Custom tools always check for updates."""
        return True

    def perform_update(self) -> UpdateResult:
        """Execute custom update script."""
        old_version = self.get_current_version()

        if not self.script_path:
            return UpdateResult(
                success=False,
                tool_name=self.tool.name,
                old_version=old_version,
                error_message=f"No custom script found for {self.tool.name}"
            )

        try:
            # Set up environment
            env = os.environ.copy()
            env['ARCH'] = detect_architecture()
            env['TOOL_NAME'] = self.tool.name
            env['TOOL_PATH'] = str(self.tool.path)

            result = subprocess.run(
                ['bash', str(self.script_path)],
                capture_output=True, text=True, timeout=600,
                env=env
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
                error_message="Custom script timed out",
            )
        except Exception as e:
            return UpdateResult(
                success=False,
                tool_name=self.tool.name,
                old_version=old_version,
                error_message=str(e),
            )
