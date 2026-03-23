"""
CRITICAL: Path protection and safety checks for pwncloudos-sync.

This module ensures that launcher files and other protected paths
are NEVER modified by the updater.
"""

import fnmatch
import os
from pathlib import Path
from typing import List
import logging

logger = logging.getLogger('pwncloudos-sync')


class ProtectedPathError(Exception):
    """Raised when attempting to modify a protected path."""
    pass


class UnauthorizedPathError(Exception):
    """Raised when attempting to modify an unauthorized path."""
    pass


# THESE PATHS MUST NEVER BE MODIFIED BY THE UPDATER
PROTECTED_PATHS: List[str] = [
    # Launcher scripts - documentation only, not actual tools
    "**/docs/configs/launchers/**/*.sh",
    "**/docs/configs/launchers/**/*.desktop",

    # Shell configurations - user customizations
    "**/docs/configs/shell/**",
    "**/.zshrc",
    "**/.bashrc",
    "**/.profile",

    # Desktop environment configs - user preferences
    "**/docs/configs/xfce/**",
    "**/docs/configs/menulibre/**",

    # System desktop files
    "/usr/share/applications/*.desktop",
    "~/.local/share/applications/*.desktop",

    # Config files
    "**/*.conf",
    "**/config.yaml",
    "**/config.yml",
]

# THESE ARE THE ONLY PATHS THE UPDATER CAN MODIFY
ALLOWED_UPDATE_PATHS: List[str] = [
    "/opt/aws_tools/*",
    "/opt/azure_tools/*",
    "/opt/gcp_tools/*",
    "/opt/multi_cloud_tools/*",
    "/opt/ps_tools/*",
    "/opt/code_scanning/*",
    "/opt/cracking-tools/*",
    "~/.local/bin",
    "/home/*/.local/bin",
    "~/.local/bin/*",
    "/home/*/.local/bin/*",
    "~/.local/pipx/venvs/*",
    "/home/*/.local/pipx/venvs/*",
    "/usr/local/bin/steampipe",
    "/usr/local/bin/powerpipe",
    "~/go/bin/*",
    "/home/*/go/bin/*",
]


def is_path_protected(path: Path) -> bool:
    """
    Check if a path is protected from modification.

    CRITICAL: This function must ALWAYS err on the side of protection.
    If in doubt, the path is protected.

    Args:
        path: Path to check

    Returns:
        bool: True if the path is protected
    """
    path_str = str(path.resolve())

    # Expand home directory
    path_str = os.path.expanduser(path_str)

    # Check against protected patterns
    for pattern in PROTECTED_PATHS:
        expanded_pattern = os.path.expanduser(pattern)
        if fnmatch.fnmatch(path_str, expanded_pattern):
            logger.debug(f"Path {path_str} matches protected pattern: {pattern}")
            return True

    # Additional hard-coded checks
    if 'launcher' in path_str.lower():
        logger.debug(f"Path {path_str} contains 'launcher' - protected")
        return True

    if path_str.endswith('.desktop'):
        logger.debug(f"Path {path_str} is a .desktop file - protected")
        return True

    if '/docs/configs/' in path_str:
        logger.debug(f"Path {path_str} is in docs/configs/ - protected")
        return True

    return False


def is_path_allowed(path: Path) -> bool:
    """
    Check if a path is in the allowed update locations.

    Args:
        path: Path to check

    Returns:
        bool: True if the path is in allowed locations
    """
    path_str = str(path.resolve())
    path_str = os.path.expanduser(path_str)

    for pattern in ALLOWED_UPDATE_PATHS:
        expanded_pattern = os.path.expanduser(pattern)
        if fnmatch.fnmatch(path_str, expanded_pattern):
            return True

    return False


def validate_update_target(path: Path) -> None:
    """
    Validate that a path is safe to update.

    This function MUST be called before ANY file modification.

    Args:
        path: Path to validate

    Raises:
        ProtectedPathError: If the path is protected
        UnauthorizedPathError: If the path is not in allowed locations
    """
    path = Path(path)

    # Check if path is protected
    if is_path_protected(path):
        raise ProtectedPathError(
            f"REFUSED: Cannot modify protected path: {path}\n"
            f"This path contains launcher scripts or configuration files.\n"
            f"Only tool directories in /opt/ can be updated."
        )

    # Check if path is in allowed locations
    if not is_path_allowed(path):
        raise UnauthorizedPathError(
            f"REFUSED: Path not in allowed update locations: {path}\n"
            f"Allowed locations: /opt/*_tools/, ~/.local/bin/, ~/.local/pipx/venvs/, /usr/local/bin/"
        )

    logger.debug(f"Path validated for update: {path}")


def safe_write(path: Path, content: str) -> None:
    """
    Safely write content to a file, with protection checks.

    Args:
        path: Path to write to
        content: Content to write

    Raises:
        ProtectedPathError: If the path is protected
        UnauthorizedPathError: If the path is not in allowed locations
    """
    validate_update_target(path)
    path.write_text(content)


def safe_delete(path: Path) -> None:
    """
    Safely delete a file, with protection checks.

    Args:
        path: Path to delete

    Raises:
        ProtectedPathError: If the path is protected
        UnauthorizedPathError: If the path is not in allowed locations
    """
    validate_update_target(path)
    if path.exists():
        path.unlink()
