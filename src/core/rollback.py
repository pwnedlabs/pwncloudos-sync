"""
Rollback engine for pwncloudos-sync.
"""

import shutil
import tarfile
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
import logging

logger = logging.getLogger('pwncloudos-sync')


@dataclass
class RollbackData:
    """Data needed to rollback an update."""
    tool_name: str
    backup_path: Path
    original_version: str
    backup_timestamp: datetime
    backup_type: str  # 'directory', 'file', 'git_state', 'pipx_state'


class RollbackEngine:
    """Manages backups and rollbacks for tool updates."""

    def __init__(self, backup_dir: Path):
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.active_backups: Dict[str, RollbackData] = {}

    def create_backup(self, tool, updater) -> RollbackData:
        """
        Create a backup before updating a tool.

        Args:
            tool: Tool object
            updater: Updater instance

        Returns:
            RollbackData for restoration
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{tool.name}_{timestamp}"

        if tool.install_method in ('git', 'git_python'):
            rollback_data = self._backup_git_state(tool, backup_name)
        elif tool.install_method == 'pipx':
            rollback_data = self._backup_pipx_state(tool, backup_name)
        elif tool.install_method == 'binary':
            rollback_data = self._backup_file(tool.path, backup_name)
        elif tool.install_method == 'file_replacement':
            rollback_data = self._backup_files(tool.path, backup_name)
        else:
            rollback_data = self._backup_directory(tool.path, backup_name)

        self.active_backups[tool.name] = rollback_data
        return rollback_data

    def restore(self, rollback_data: RollbackData) -> bool:
        """
        Restore a tool from backup.

        Args:
            rollback_data: Data from create_backup

        Returns:
            bool: True if restore succeeded
        """
        logger.info(f"Rolling back {rollback_data.tool_name}...")

        try:
            if rollback_data.backup_type == 'git_state':
                return self._restore_git_state(rollback_data)
            elif rollback_data.backup_type == 'pipx_state':
                return self._restore_pipx_state(rollback_data)
            elif rollback_data.backup_type == 'file':
                return self._restore_file(rollback_data)
            elif rollback_data.backup_type == 'files':
                return self._restore_files(rollback_data)
            elif rollback_data.backup_type == 'directory':
                return self._restore_directory(rollback_data)
            else:
                logger.error(f"Unknown backup type: {rollback_data.backup_type}")
                return False
        except Exception as e:
            logger.error(f"Rollback failed for {rollback_data.tool_name}: {e}")
            return False

    def cleanup_old_backups(self, keep_count: int = 3) -> None:
        """
        Remove old backups, keeping most recent N per tool.

        Args:
            keep_count: Number of backups to keep per tool
        """
        # Group backups by tool name
        tool_backups: Dict[str, list] = {}

        for item in self.backup_dir.iterdir():
            if item.name.startswith('.'):
                continue

            # Parse tool name from backup name (format: toolname_timestamp)
            parts = item.name.rsplit('_', 2)
            if len(parts) >= 2:
                tool_name = '_'.join(parts[:-2]) if len(parts) > 2 else parts[0]
                if tool_name not in tool_backups:
                    tool_backups[tool_name] = []
                tool_backups[tool_name].append(item)

        # Keep only recent backups
        for tool_name, backups in tool_backups.items():
            # Sort by modification time, newest first
            backups.sort(key=lambda p: p.stat().st_mtime, reverse=True)

            # Remove old backups
            for backup in backups[keep_count:]:
                logger.debug(f"Removing old backup: {backup}")
                if backup.is_dir():
                    shutil.rmtree(backup)
                else:
                    backup.unlink()

    def _backup_git_state(self, tool, backup_name: str) -> RollbackData:
        """Record git commit for rollback."""
        result = subprocess.run(
            ['git', '-C', str(tool.path), 'rev-parse', 'HEAD'],
            capture_output=True, text=True
        )
        commit = result.stdout.strip()

        state_file = self.backup_dir / f"{backup_name}.json"
        state_file.write_text(json.dumps({
            'commit': commit,
            'path': str(tool.path),
            'remote': self._get_git_remote(tool.path),
        }))

        return RollbackData(
            tool_name=tool.name,
            backup_path=state_file,
            original_version=commit[:7],
            backup_timestamp=datetime.now(),
            backup_type='git_state',
        )

    def _backup_pipx_state(self, tool, backup_name: str) -> RollbackData:
        """Record pipx package version for rollback."""
        result = subprocess.run(
            ['pipx', 'list', '--json'],
            capture_output=True, text=True
        )

        version = "unknown"
        if result.returncode == 0:
            data = json.loads(result.stdout)
            venv = data.get('venvs', {}).get(tool.pypi_name, {})
            version = venv.get('metadata', {}).get('main_package', {}).get('version', 'unknown')

        state_file = self.backup_dir / f"{backup_name}.json"
        state_file.write_text(json.dumps({
            'package': tool.pypi_name,
            'version': version,
        }))

        return RollbackData(
            tool_name=tool.name,
            backup_path=state_file,
            original_version=version,
            backup_timestamp=datetime.now(),
            backup_type='pipx_state',
        )

    def _backup_file(self, path: Path, backup_name: str) -> RollbackData:
        """Backup a single file."""
        backup_path = self.backup_dir / f"{backup_name}.backup"
        if path.exists():
            shutil.copy2(path, backup_path)
            original_version = "file"
        else:
            # Fresh install path: keep a sentinel so rollback logic has state.
            backup_path.write_text("MISSING")
            original_version = "missing"

        return RollbackData(
            tool_name=backup_name.split('_')[0],
            backup_path=backup_path,
            original_version=original_version,
            backup_timestamp=datetime.now(),
            backup_type='file',
        )

    def _backup_files(self, tool_path: Path, backup_name: str) -> RollbackData:
        """Backup specific files from a tool directory."""
        backup_dir = self.backup_dir / backup_name
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Backup Python files and requirements
        for pattern in ['*.py', 'requirements.txt']:
            for file in tool_path.glob(pattern):
                shutil.copy2(file, backup_dir / file.name)

        return RollbackData(
            tool_name=backup_name.split('_')[0],
            backup_path=backup_dir,
            original_version="files",
            backup_timestamp=datetime.now(),
            backup_type='files',
        )

    def _backup_directory(self, path: Path, backup_name: str) -> RollbackData:
        """Create tarball backup of directory."""
        backup_path = self.backup_dir / f"{backup_name}.tar.gz"

        with tarfile.open(backup_path, "w:gz") as tar:
            tar.add(path, arcname=path.name)

        return RollbackData(
            tool_name=backup_name.split('_')[0],
            backup_path=backup_path,
            original_version="directory",
            backup_timestamp=datetime.now(),
            backup_type='directory',
        )

    def _restore_git_state(self, rollback_data: RollbackData) -> bool:
        """Restore git repository to previous commit."""
        state = json.loads(rollback_data.backup_path.read_text())
        commit = state['commit']
        path = state['path']

        result = subprocess.run(
            ['git', '-C', path, 'reset', '--hard', commit],
            capture_output=True, text=True
        )

        return result.returncode == 0

    def _restore_pipx_state(self, rollback_data: RollbackData) -> bool:
        """Restore pipx package to previous version."""
        state = json.loads(rollback_data.backup_path.read_text())
        package = state['package']
        version = state['version']

        if version == "unknown":
            return False

        # Uninstall current and install specific version
        subprocess.run(['pipx', 'uninstall', package], capture_output=True)
        result = subprocess.run(
            ['pipx', 'install', f"{package}=={version}"],
            capture_output=True, text=True
        )

        return result.returncode == 0

    def _restore_file(self, rollback_data: RollbackData) -> bool:
        """Restore a single file from backup."""
        # Extract original path from tool info
        # This is a simplified version - real implementation would store original path
        return False  # Placeholder

    def _restore_files(self, rollback_data: RollbackData) -> bool:
        """Restore specific files from backup."""
        backup_dir = rollback_data.backup_path
        # Tool path needs to be determined from backup metadata
        return False  # Placeholder

    def _restore_directory(self, rollback_data: RollbackData) -> bool:
        """Restore directory from tarball."""
        # This would extract the tarball to the original location
        return False  # Placeholder

    def _get_git_remote(self, path: Path) -> str:
        """Get the git remote URL."""
        result = subprocess.run(
            ['git', '-C', str(path), 'remote', 'get-url', 'origin'],
            capture_output=True, text=True
        )
        return result.stdout.strip()
