"""
Git repository updater for pwncloudos-sync.

IMPORTANT: git operations (pull, reset --hard) can destroy custom PwnCloudOS
files that live inside tool directories (e.g. *_Launcher.ps1 scripts).
All git mutations MUST be wrapped with _backup_launcher_files / _restore_launcher_files.
NEVER use `git clean` — it would remove untracked launcher files.
"""

import os
import stat
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from .base import BaseUpdater, UpdateResult


class GitUpdater(BaseUpdater):
    """Updater for git repositories."""

    # ------------------------------------------------------------------ #
    # Launcher file protection
    # ------------------------------------------------------------------ #

    def _find_launcher_files(self, tool_path: Path) -> List[Path]:
        """
        Find custom PwnCloudOS launcher files inside the tool directory.

        Matches pattern-based (case-insensitive): *Launcher*, *_launcher*
        Also matches .ps1 files that are NOT tracked by the git repo.
        """
        launchers: List[Path] = []
        tool_path = Path(tool_path)

        if not tool_path.is_dir():
            return launchers

        # Pattern-based: anything matching *launcher* (case-insensitive)
        for f in tool_path.rglob('*'):
            if f.is_file() and 'launcher' in f.name.lower():
                launchers.append(f)

        # Untracked .ps1 files (custom PwnCloudOS additions not in upstream)
        try:
            result = subprocess.run(
                ['git', '-C', str(tool_path), 'ls-files', '--others', '--exclude-standard', '*.ps1'],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                for line in result.stdout.strip().splitlines():
                    if line:
                        p = tool_path / line
                        if p.is_file() and p not in launchers:
                            launchers.append(p)
        except Exception:
            pass

        return launchers

    def _backup_launcher_files(self, tool_path: Path) -> Dict[Path, Tuple[bytes, int]]:
        """
        Read launcher files into memory before git operations.

        Returns:
            Dict mapping absolute path -> (file content bytes, permission mode)
        """
        backups: Dict[Path, Tuple[bytes, int]] = {}
        for f in self._find_launcher_files(tool_path):
            try:
                backups[f] = (f.read_bytes(), f.stat().st_mode)
            except OSError as e:
                self.logger.warning(f"Could not backup launcher file {f}: {e}")
        if backups:
            self.logger.info(f"Backed up {len(backups)} launcher file(s) before git operation")
        return backups

    def _restore_launcher_files(self, backups: Dict[Path, Tuple[bytes, int]]) -> None:
        """Restore launcher files after git operations, preserving original permissions."""
        for fpath, (content, mode) in backups.items():
            try:
                fpath.parent.mkdir(parents=True, exist_ok=True)
                fpath.write_bytes(content)
                os.chmod(fpath, stat.S_IMODE(mode))
            except OSError as e:
                self.logger.error(f"CRITICAL: Failed to restore launcher file {fpath}: {e}")
        if backups:
            self.logger.info(f"Restored {len(backups)} launcher file(s) after git operation")

    # ------------------------------------------------------------------ #
    # Version detection
    # ------------------------------------------------------------------ #

    def get_current_version(self) -> Optional[str]:
        """Get current commit hash."""
        try:
            result = subprocess.run(
                ['git', '-C', str(self.tool.path), 'rev-parse', '--short', 'HEAD'],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception as e:
            self.logger.debug(f"Failed to get current version: {e}")
        return None

    def get_latest_version(self) -> Optional[str]:
        """Get latest commit hash from remote."""
        try:
            # Fetch first — check return code
            fetch = subprocess.run(
                ['git', '-C', str(self.tool.path), 'fetch', 'origin'],
                capture_output=True, text=True, timeout=60
            )
            if fetch.returncode != 0:
                self.logger.warning(f"git fetch failed: {fetch.stderr.strip()}")
                return None

            # Get remote HEAD
            result = subprocess.run(
                ['git', '-C', str(self.tool.path), 'rev-parse', '--short', 'origin/HEAD'],
                capture_output=True, text=True
            )

            if result.returncode != 0:
                # Try origin/main or origin/master
                for branch in ['origin/main', 'origin/master']:
                    result = subprocess.run(
                        ['git', '-C', str(self.tool.path), 'rev-parse', '--short', branch],
                        capture_output=True, text=True
                    )
                    if result.returncode == 0:
                        return result.stdout.strip()

            return result.stdout.strip() if result.returncode == 0 else None
        except Exception as e:
            self.logger.debug(f"Failed to get latest version: {e}")
        return None

    def needs_update(self) -> bool:
        """Check if there are new commits."""
        try:
            # Fetch first — check return code
            fetch = subprocess.run(
                ['git', '-C', str(self.tool.path), 'fetch', 'origin'],
                capture_output=True, text=True, timeout=60
            )
            if fetch.returncode != 0:
                self.logger.warning(f"git fetch failed: {fetch.stderr.strip()}")
                return False

            # Count commits behind
            result = subprocess.run(
                ['git', '-C', str(self.tool.path), 'rev-list', 'HEAD...origin/HEAD', '--count'],
                capture_output=True, text=True
            )

            if result.returncode != 0:
                # Try with explicit branch
                result = subprocess.run(
                    ['git', '-C', str(self.tool.path), 'rev-list', 'HEAD...origin/main', '--count'],
                    capture_output=True, text=True
                )

            if result.returncode == 0:
                count = int(result.stdout.strip())
                return count > 0
        except Exception as e:
            self.logger.debug(f"Failed to check for updates: {e}")

        return False

    def perform_update(self) -> UpdateResult:
        """Execute git pull, protecting launcher files."""
        old_version = self.get_current_version()

        # Protect launcher files before ANY git mutation
        launcher_backups = self._backup_launcher_files(self.tool.path)

        try:
            # Try git pull first (use tracked upstream, not 'origin HEAD')
            result = subprocess.run(
                ['git', '-C', str(self.tool.path), 'pull'],
                capture_output=True, text=True, timeout=120
            )

            if result.returncode != 0:
                # If pull fails, try reset --hard
                self.logger.warning("git pull failed, trying reset --hard")
                result = subprocess.run(
                    ['git', '-C', str(self.tool.path), 'reset', '--hard', 'origin/HEAD'],
                    capture_output=True, text=True, timeout=60
                )

                if result.returncode != 0:
                    # Try with explicit branch
                    result = subprocess.run(
                        ['git', '-C', str(self.tool.path), 'reset', '--hard', 'origin/main'],
                        capture_output=True, text=True, timeout=60
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
                error_message="Git operation timed out",
            )
        except Exception as e:
            return UpdateResult(
                success=False,
                tool_name=self.tool.name,
                old_version=old_version,
                error_message=str(e),
            )
        finally:
            # ALWAYS restore launcher files, even on failure
            if launcher_backups:
                self._restore_launcher_files(launcher_backups)

    def verify_update(self) -> bool:
        """Verify git repository is in good state."""
        try:
            result = subprocess.run(
                ['git', '-C', str(self.tool.path), 'status'],
                capture_output=True, timeout=10
            )
            return result.returncode == 0
        except Exception:
            return False
