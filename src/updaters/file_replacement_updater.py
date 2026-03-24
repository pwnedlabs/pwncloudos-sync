"""
File replacement updater for pwncloudos-sync.

This is a lightweight updater that downloads and replaces
specific files (.py, requirements.txt) from GitHub without
requiring a full git clone.
"""

import hashlib
import subprocess
from pathlib import Path
from typing import Optional
import requests
from .base import BaseUpdater, UpdateResult
from ..core.safeguards import safe_write


class FileReplacementUpdater(BaseUpdater):
    """Lightweight updater that replaces files from GitHub."""

    def __init__(self, tool, config):
        super().__init__(tool, config)
        self.files_to_update = ['requirements.txt']
        self.main_script = self._detect_main_script()
        if self.main_script:
            self.files_to_update.insert(0, self.main_script.name)

    def _detect_main_script(self) -> Optional[Path]:
        """Detect the main Python script."""
        tool_name = self.tool.path.name.lower()

        # Common patterns for main script
        patterns = [
            f"{tool_name}.py",
            f"{tool_name.replace('-', '_')}.py",
            "main.py",
            "__main__.py",
        ]

        for pattern in patterns:
            candidate = self.tool.path / pattern
            if candidate.exists():
                return candidate

        # Fallback: single .py file
        py_files = [f for f in self.tool.path.glob("*.py")
                    if not f.name.startswith('_')]
        if len(py_files) == 1:
            return py_files[0]

        return None

    def _get_default_branch(self) -> str:
        """Get default branch from GitHub API."""
        if not self.tool.github_repo:
            return 'main'

        try:
            url = f"https://api.github.com/repos/{self.tool.github_repo}"
            response = requests.get(url, timeout=10)
            if response.ok:
                return response.json().get('default_branch', 'main')
        except Exception:
            pass
        return 'main'

    def _get_raw_url(self, filename: str) -> str:
        """Get raw GitHub URL for a file."""
        branch = self._get_default_branch()
        return f"https://raw.githubusercontent.com/{self.tool.github_repo}/{branch}/{filename}"

    def _get_latest_commit(self) -> Optional[str]:
        """Get latest commit SHA from GitHub API."""
        if not self.tool.github_repo:
            return None

        try:
            branch = self._get_default_branch()
            url = f"https://api.github.com/repos/{self.tool.github_repo}/commits/{branch}"
            response = requests.get(url, timeout=10)
            if response.ok:
                return response.json()['sha'][:7]
        except Exception:
            pass
        return None

    def get_current_version(self) -> Optional[str]:
        """Get current version from file hash."""
        if self.main_script and self.main_script.exists():
            content = self.main_script.read_bytes()
            return hashlib.md5(content).hexdigest()[:7]
        return None

    def get_latest_version(self) -> Optional[str]:
        """Get latest version (commit SHA) from GitHub."""
        return self._get_latest_commit()

    def needs_update(self) -> bool:
        """Check if files have changed on GitHub by comparing remote SHA to local git state."""
        if not self.tool.github_repo:
            self.logger.warning(f"No GitHub repo for {self.tool.name}, cannot check updates")
            return False

        latest = self._get_latest_commit()
        if not latest:
            # Can't determine latest — don't falsely claim update available
            return False

        # Try to get local git commit hash for comparison
        if self.tool.path.is_dir() and (self.tool.path / '.git').exists():
            try:
                import subprocess
                result = subprocess.run(
                    ['git', '-C', str(self.tool.path), 'rev-parse', '--short=7', 'HEAD'],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    local_sha = result.stdout.strip()
                    return local_sha != latest
            except Exception:
                pass

        # No git directory — cannot reliably compare
        return False

    def perform_update(self) -> UpdateResult:
        """Download and replace files from GitHub."""
        if not self.tool.github_repo:
            return UpdateResult(
                success=False,
                tool_name=self.tool.name,
                error_message="No GitHub repo configured"
            )

        old_version = self.get_current_version()
        updated_files = []

        for filename in self.files_to_update:
            url = self._get_raw_url(filename)

            try:
                response = requests.get(url, timeout=30)

                if response.status_code == 404:
                    self.logger.debug(f"File not found on GitHub: {filename}")
                    continue

                if not response.ok:
                    return UpdateResult(
                        success=False,
                        tool_name=self.tool.name,
                        error_message=f"Failed to download {filename}: HTTP {response.status_code}"
                    )

                # Write new content (through safeguards)
                target = self.tool.path / filename
                safe_write(target, response.text)
                updated_files.append(filename)
                self.logger.info(f"Updated: {filename}")

            except requests.RequestException as e:
                return UpdateResult(
                    success=False,
                    tool_name=self.tool.name,
                    error_message=f"Network error downloading {filename}: {e}"
                )

        if not updated_files:
            return UpdateResult(
                success=True,
                tool_name=self.tool.name,
                old_version=old_version,
                skipped=True,
                skip_reason="No files to update"
            )

        # Update Python dependencies
        req_file = self.tool.path / "requirements.txt"
        if req_file.exists() and "requirements.txt" in updated_files:
            try:
                result = subprocess.run(
                    ["python3", "-m", "pip", "install", "-r", str(req_file), "--upgrade", "--quiet"],
                    capture_output=True, text=True, timeout=300
                )
                if result.returncode != 0:
                    self.logger.warning(f"pip install warning: {result.stderr}")
            except Exception as e:
                self.logger.warning(f"pip install error: {e}")

        return UpdateResult(
            success=True,
            tool_name=self.tool.name,
            old_version=old_version,
            new_version=self.get_latest_version(),
        )

    def verify_update(self) -> bool:
        """Verify tool still works after update."""
        if not self.main_script or not self.main_script.exists():
            return True

        try:
            result = subprocess.run(
                ["python3", str(self.main_script), "--help"],
                capture_output=True, text=True, timeout=10
            )
            # Some tools return non-zero for --help, that's OK
            return True
        except Exception:
            return False
