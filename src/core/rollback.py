"""
Rollback engine for pwncloudos-sync.
"""

import shutil
import tarfile
import json
import os
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
    backup_type: str  # 'directory', 'file', 'files', 'git_state', 'pipx_state'
    original_path: Optional[Path] = None  # Where to restore to


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

        # Store tool name so child _backup_* methods can use it directly
        # instead of parsing from backup_name (which breaks for hyphenated names).
        self._current_tool_name = tool.name

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

        # Write sidecar metadata for cleanup_old_backups to identify tool name
        try:
            meta_file = self.backup_dir / f"{rollback_data.backup_path.stem}.meta.json"
            meta_file.write_text(json.dumps({
                'tool_name': tool.name,
                'original_path': str(tool.path),
                'backup_type': rollback_data.backup_type,
                'timestamp': rollback_data.backup_timestamp.isoformat(),
            }))
        except Exception:
            pass  # Non-critical: cleanup may not group correctly, but backup/restore still works

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
        # Group backups by tool name using the known active_backups tool names.
        # Also check for sidecar metadata written during create_backup.
        tool_backups: Dict[str, list] = {}

        for item in self.backup_dir.iterdir():
            if item.name.startswith('.'):
                continue

            # Try to read sidecar metadata
            meta_file = self.backup_dir / (item.stem + '.meta.json') if not item.name.endswith('.meta.json') else None
            tool_name = None

            if meta_file and meta_file.exists():
                try:
                    meta = json.loads(meta_file.read_text())
                    tool_name = meta.get('tool_name')
                except Exception:
                    pass

            if not tool_name:
                # Fallback: try to match against known tool names from active_backups
                for known_name in self.active_backups:
                    if item.name.startswith(known_name + '_'):
                        tool_name = known_name
                        break

            if not tool_name:
                # Skip metadata files themselves and unrecognizable items
                if item.name.endswith('.meta.json'):
                    continue
                # Last resort: best-effort parse (timestamp is YYYYMMDD_HHMMSS)
                name = item.stem
                # Try to split off the last two underscore-separated groups as timestamp
                parts = name.rsplit('_', 2)
                if len(parts) >= 3 and parts[-2].isdigit() and parts[-1].isdigit():
                    tool_name = '_'.join(parts[:-2])
                elif len(parts) >= 2 and parts[-1].isdigit():
                    tool_name = '_'.join(parts[:-1])
                else:
                    tool_name = name

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
                    # Also remove sidecar metadata if present
                    meta = self.backup_dir / (backup.stem + '.meta.json')
                    if meta.exists():
                        meta.unlink()

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
        venvs = self._load_pipx_venvs()
        package_name = self._resolve_pipx_package_name(tool, venvs)
        managed_by_pipx = bool(package_name)
        version = "not-installed"

        if package_name:
            venv = venvs.get(package_name, {})
            version = venv.get('metadata', {}).get('main_package', {}).get('version', 'unknown')

        state_file = self.backup_dir / f"{backup_name}.json"
        state_file.write_text(json.dumps({
            'package': package_name or tool.pypi_name,
            'version': version,
            'managed_by_pipx': managed_by_pipx,
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
            tool_name=self._current_tool_name,
            backup_path=backup_path,
            original_version=original_version,
            backup_timestamp=datetime.now(),
            backup_type='file',
            original_path=path,
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
            tool_name=self._current_tool_name,
            backup_path=backup_dir,
            original_version="files",
            backup_timestamp=datetime.now(),
            backup_type='files',
            original_path=tool_path,
        )

    def _backup_directory(self, path: Path, backup_name: str) -> RollbackData:
        """Create tarball backup of directory."""
        backup_path = self.backup_dir / f"{backup_name}.tar.gz"

        with tarfile.open(backup_path, "w:gz") as tar:
            tar.add(path, arcname=path.name)

        return RollbackData(
            tool_name=self._current_tool_name,
            backup_path=backup_path,
            original_version="directory",
            backup_timestamp=datetime.now(),
            backup_type='directory',
            original_path=path,
        )

    def _needs_sudo(self, path: str) -> bool:
        """Check if operations on this path need sudo."""
        if os.geteuid() == 0:
            return False
        return str(path).startswith('/opt/')

    def _restore_git_state(self, rollback_data: RollbackData) -> bool:
        """Restore git repository to previous commit."""
        state = json.loads(rollback_data.backup_path.read_text())
        commit = state['commit']
        path = state['path']

        cmd = ['git', '-C', path, 'reset', '--hard', commit]
        if self._needs_sudo(path):
            cmd = ['sudo'] + cmd

        result = subprocess.run(
            cmd,
            capture_output=True, text=True
        )

        return result.returncode == 0

    def _restore_pipx_state(self, rollback_data: RollbackData) -> bool:
        """Restore pipx package to previous version."""
        state = json.loads(rollback_data.backup_path.read_text())
        package = state['package']
        version = state['version']
        managed_by_pipx = state.get('managed_by_pipx', True)

        if not managed_by_pipx:
            return True

        if not package or version in ("unknown", "not-installed"):
            return True

        # Uninstall current and install specific version
        subprocess.run(['pipx', 'uninstall', package], capture_output=True, text=True)
        result = subprocess.run(
            ['pipx', 'install', f"{package}=={version}"],
            capture_output=True, text=True
        )

        return result.returncode == 0

    def _restore_file(self, rollback_data: RollbackData) -> bool:
        """Restore a single file from backup."""
        if not rollback_data.original_path:
            logger.error("Cannot restore file: original_path not recorded in backup")
            return False

        backup = rollback_data.backup_path
        target = Path(rollback_data.original_path)

        if not backup.exists():
            logger.error(f"Backup file not found: {backup}")
            return False

        # If the backup was a sentinel for a missing file, remove the installed copy
        if backup.read_text().strip() == "MISSING":
            if target.exists():
                if self._needs_sudo(str(target)):
                    subprocess.run(['sudo', 'rm', str(target)], capture_output=True)
                else:
                    target.unlink()
            return True

        target.parent.mkdir(parents=True, exist_ok=True)
        if self._needs_sudo(str(target)):
            subprocess.run(['sudo', 'cp', '-p', str(backup), str(target)], capture_output=True)
        else:
            shutil.copy2(backup, target)
        return True

    def _restore_files(self, rollback_data: RollbackData) -> bool:
        """Restore specific files from backup directory."""
        if not rollback_data.original_path:
            logger.error("Cannot restore files: original_path not recorded in backup")
            return False

        backup_dir = rollback_data.backup_path
        target_dir = Path(rollback_data.original_path)

        if not backup_dir.exists() or not backup_dir.is_dir():
            logger.error(f"Backup directory not found: {backup_dir}")
            return False

        use_sudo = self._needs_sudo(str(target_dir))
        for backed_up_file in backup_dir.iterdir():
            if backed_up_file.is_file():
                dest = target_dir / backed_up_file.name
                if use_sudo:
                    subprocess.run(
                        ['sudo', 'cp', '-p', str(backed_up_file), str(dest)],
                        capture_output=True
                    )
                else:
                    shutil.copy2(backed_up_file, dest)

        return True

    def _restore_directory(self, rollback_data: RollbackData) -> bool:
        """Restore directory from tarball."""
        if not rollback_data.original_path:
            logger.error("Cannot restore directory: original_path not recorded in backup")
            return False

        backup_path = rollback_data.backup_path
        target = Path(rollback_data.original_path)

        if not backup_path.exists():
            logger.error(f"Backup tarball not found: {backup_path}")
            return False

        use_sudo = self._needs_sudo(str(target))

        # Remove the current version of the directory
        if target.exists():
            if use_sudo:
                subprocess.run(['sudo', 'rm', '-rf', str(target)], capture_output=True)
            else:
                shutil.rmtree(target)

        # Extract tarball to the parent directory (arcname was dir.name)
        if use_sudo:
            subprocess.run(
                ['sudo', 'tar', '-xzf', str(backup_path), '-C', str(target.parent)],
                capture_output=True
            )
        else:
            with tarfile.open(backup_path, "r:gz") as tar:
                tar.extractall(target.parent)

        return True

    def _get_git_remote(self, path: Path) -> str:
        """Get the git remote URL."""
        result = subprocess.run(
            ['git', '-C', str(path), 'remote', 'get-url', 'origin'],
            capture_output=True, text=True
        )
        return result.stdout.strip()

    def _load_pipx_venvs(self) -> Dict[str, dict]:
        """Load pipx metadata, returning empty data on failure."""
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
        except Exception:
            pass

        return {}

    def _resolve_pipx_package_name(self, tool, venvs: Dict[str, dict]) -> Optional[str]:
        """Resolve the installed pipx package associated with a tool."""
        if tool.pypi_name and tool.pypi_name in venvs:
            return tool.pypi_name

        command_name = tool.version_command.split()[0] if tool.version_command else Path(tool.path).name
        target_path = Path(tool.path).expanduser().resolve(strict=False).as_posix()

        for pkg_name, pkg_info in venvs.items():
            metadata = pkg_info.get('metadata', {})
            main_package = metadata.get('main_package', {})
            app_paths = main_package.get('app_paths', [])
            app_names = set(main_package.get('apps', []))

            if command_name and command_name in app_names:
                return pkg_name

            for app in app_paths:
                try:
                    if Path(app).expanduser().resolve(strict=False).as_posix() == target_path:
                        return pkg_name
                except Exception:
                    continue

        return None
