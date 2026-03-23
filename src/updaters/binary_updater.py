"""
Binary download updater for pwncloudos-sync.
"""

import os
import shutil
import subprocess
import tempfile
import tarfile
import zipfile
from pathlib import Path
from typing import Optional
import requests
from .base import BaseUpdater, UpdateResult
from ..core.arch import detect_architecture, get_binary_asset_pattern


class BinaryUpdater(BaseUpdater):
    """Updater for binary tools from GitHub releases."""

    def get_current_version(self) -> Optional[str]:
        """Get current version from binary --version."""
        if self.tool.version_command:
            try:
                result = subprocess.run(
                    self.tool.version_command.split(),
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    # Extract version from output
                    output = result.stdout + result.stderr
                    import re
                    match = re.search(r'v?(\d+\.\d+\.?\d*)', output)
                    if match:
                        return match.group(1)
            except Exception as e:
                self.logger.debug(f"Failed to get current version: {e}")
        return None

    def get_latest_version(self) -> Optional[str]:
        """Get latest version from GitHub releases."""
        if not self.tool.github_repo:
            return None

        try:
            url = f"https://api.github.com/repos/{self.tool.github_repo}/releases/latest"
            response = requests.get(url, timeout=10)

            if response.ok:
                data = response.json()
                tag = data.get('tag_name', '')
                # Remove 'v' prefix if present
                return tag.lstrip('v')
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

    def _get_download_url(self) -> Optional[str]:
        """Get download URL for current architecture."""
        if not self.tool.github_repo:
            return None

        try:
            arch = detect_architecture()
            url = f"https://api.github.com/repos/{self.tool.github_repo}/releases/latest"
            response = requests.get(url, timeout=10)

            if not response.ok:
                return None

            data = response.json()
            assets = data.get('assets', [])

            # Get pattern for this tool and arch
            try:
                pattern_info = get_binary_asset_pattern(self.tool.name, arch)
                pattern = pattern_info['pattern']
            except ValueError:
                # No predefined pattern, try to find matching asset
                arch_keywords = ['linux', arch]
                if arch == 'amd64':
                    arch_keywords.extend(['x86_64', 'amd64'])
                elif arch == 'arm64':
                    arch_keywords.extend(['aarch64', 'arm64'])

                for asset in assets:
                    name = asset['name'].lower()
                    if all(kw in name for kw in arch_keywords):
                        return asset['browser_download_url']
                return None

            # Find matching asset
            import fnmatch
            for asset in assets:
                if fnmatch.fnmatch(asset['name'], pattern) or fnmatch.fnmatch(asset['name'], pattern.replace('*', '')):
                    return asset['browser_download_url']

            # Fallback: try pattern without wildcards
            for asset in assets:
                if arch in asset['name'].lower() and 'linux' in asset['name'].lower():
                    return asset['browser_download_url']

        except Exception as e:
            self.logger.debug(f"Failed to get download URL: {e}")
        return None

    def perform_update(self) -> UpdateResult:
        """Download and install new binary."""
        old_version = self.get_current_version()

        download_url = self._get_download_url()
        if not download_url:
            return UpdateResult(
                success=False,
                tool_name=self.tool.name,
                old_version=old_version,
                error_message="Could not find download URL for current architecture"
            )

        try:
            # Download to temp file
            self.logger.info(f"Downloading from {download_url}")
            response = requests.get(download_url, timeout=300, stream=True)

            if not response.ok:
                return UpdateResult(
                    success=False,
                    tool_name=self.tool.name,
                    old_version=old_version,
                    error_message=f"Download failed: HTTP {response.status_code}"
                )

            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                for chunk in response.iter_content(chunk_size=8192):
                    tmp.write(chunk)
                tmp_path = tmp.name

            # Extract or move
            if download_url.endswith('.tar.gz') or download_url.endswith('.tgz'):
                extracted = self._extract_tarball(tmp_path)
            elif download_url.endswith('.zip'):
                extracted = self._extract_zip(tmp_path)
            else:
                # Raw binary
                extracted = tmp_path

            # Install
            target = self.tool.path
            if target.is_dir():
                # Find binary in directory
                pass  # Handle directory case
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                # Copy to target
                shutil.copy2(extracted, target)
                os.chmod(target, 0o755)

            # Cleanup
            os.unlink(tmp_path)
            if extracted != tmp_path and Path(extracted).exists():
                if Path(extracted).is_dir():
                    shutil.rmtree(extracted)
                else:
                    os.unlink(extracted)

            new_version = self.get_current_version()
            return UpdateResult(
                success=True,
                tool_name=self.tool.name,
                old_version=old_version,
                new_version=new_version,
            )

        except Exception as e:
            return UpdateResult(
                success=False,
                tool_name=self.tool.name,
                old_version=old_version,
                error_message=str(e),
            )

    def _extract_tarball(self, path: str) -> str:
        """Extract tarball and return path to binary."""
        extract_dir = tempfile.mkdtemp()
        with tarfile.open(path, 'r:gz') as tar:
            tar.extractall(extract_dir)

        # Find binary
        for root, dirs, files in os.walk(extract_dir):
            for f in files:
                fpath = os.path.join(root, f)
                if os.access(fpath, os.X_OK):
                    return fpath

        return extract_dir

    def _extract_zip(self, path: str) -> str:
        """Extract zip and return path to binary."""
        extract_dir = tempfile.mkdtemp()
        with zipfile.ZipFile(path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)

        # Find binary
        for root, dirs, files in os.walk(extract_dir):
            for f in files:
                fpath = os.path.join(root, f)
                if not f.endswith('.md') and not f.endswith('.txt'):
                    os.chmod(fpath, 0o755)
                    return fpath

        return extract_dir
