"""
Tool registry and manifest loading for pwncloudos-sync.
"""

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict
import yaml
import logging

logger = logging.getLogger('pwncloudos-sync')


@dataclass
class Tool:
    """Represents a security tool."""
    name: str
    category: str
    install_method: str  # git, git_python, pipx, binary, apt, docker, custom, file_replacement
    path: Path
    github_repo: Optional[str] = None
    pypi_name: Optional[str] = None
    apt_package: Optional[str] = None
    version_command: Optional[str] = None
    arch_support: List[str] = field(default_factory=lambda: ['amd64', 'arm64'])
    requires_compile: bool = False
    custom_handler: Optional[str] = None
    docker_compose: Optional[str] = None
    docker_image: Optional[str] = None
    ps_module_manifest: Optional[str] = None  # e.g. "AADInternals.psd1" for PowerShell tools
    enabled: bool = True


def load_tools_manifest() -> List[Tool]:
    """
    Load tools from manifest file or discover from filesystem.

    Returns:
        List of Tool objects
    """
    # Try to load from manifest
    manifest_paths = [
        Path(__file__).parent.parent.parent / 'manifests' / 'tools.yaml',
        Path('/etc/pwncloudos-sync/tools.yaml'),
    ]

    for manifest_path in manifest_paths:
        if manifest_path.exists():
            return _load_from_manifest(manifest_path)

    # Fall back to filesystem discovery
    logger.info("No manifest found, discovering tools from filesystem...")
    return _discover_tools()


def _load_from_manifest(path: Path) -> List[Tool]:
    """Load tools from YAML manifest."""
    with open(path) as f:
        data = yaml.safe_load(f)

    tools = []
    for tool_data in data.get('tools', []):
        tool = Tool(
            name=tool_data['name'],
            category=tool_data['category'],
            install_method=tool_data['install_method'],
            path=Path(tool_data['path']).expanduser(),
            github_repo=tool_data.get('github_repo'),
            pypi_name=tool_data.get('pypi_name'),
            apt_package=tool_data.get('apt_package'),
            version_command=tool_data.get('version_command'),
            arch_support=tool_data.get('arch_support', ['amd64', 'arm64']),
            requires_compile=tool_data.get('requires_compile', False),
            custom_handler=tool_data.get('custom_handler'),
            docker_compose=tool_data.get('docker_compose'),
            docker_image=tool_data.get('docker_image'),
            ps_module_manifest=tool_data.get('ps_module_manifest'),
            enabled=tool_data.get('enabled', True),
        )
        tools.append(tool)

    logger.info(f"Loaded {len(tools)} tools from manifest")
    return tools


def _discover_tools() -> List[Tool]:
    """Discover tools from filesystem."""
    tools = []

    # Scan /opt/ directories
    OPT_DIRS = {
        '/opt/aws_tools': 'aws',
        '/opt/azure_tools': 'azure',
        '/opt/gcp_tools': 'gcp',
        '/opt/multi_cloud_tools': 'multi_cloud',
        '/opt/ps_tools': 'ps_tools',
        '/opt/code_scanning': 'code_scanning',
        '/opt/cracking-tools': 'cracking',
    }

    for opt_dir, category in OPT_DIRS.items():
        opt_path = Path(opt_dir)
        if not opt_path.exists():
            continue

        for tool_dir in opt_path.iterdir():
            if not tool_dir.is_dir():
                continue

            tool = _analyze_tool_directory(tool_dir, category)
            if tool:
                tools.append(tool)

    # Discover pipx tools
    tools.extend(_discover_pipx_tools())

    logger.info(f"Discovered {len(tools)} tools from filesystem")
    return tools


def _analyze_tool_directory(path: Path, category: str) -> Optional[Tool]:
    """Analyze a tool directory and create Tool object."""
    has_git = (path / '.git').exists()
    has_requirements = (path / 'requirements.txt').exists()
    py_files = list(path.glob('*.py'))

    # Determine install method
    if has_git and has_requirements:
        install_method = 'git_python'
    elif has_git:
        install_method = 'git'
    elif py_files:
        install_method = 'file_replacement'
    else:
        install_method = 'git'  # Assume git for /opt/ tools

    # Try to get GitHub repo from git remote
    github_repo = None
    if has_git:
        github_repo = _get_github_repo_from_git(path)

    return Tool(
        name=path.name,
        category=category,
        install_method=install_method,
        path=path,
        github_repo=github_repo,
    )


def _get_github_repo_from_git(path: Path) -> Optional[str]:
    """Extract GitHub repo from git remote."""
    try:
        result = subprocess.run(
            ['git', '-C', str(path), 'remote', 'get-url', 'origin'],
            capture_output=True, text=True
        )
        url = result.stdout.strip()

        # Parse GitHub URL
        if 'github.com/' in url:
            parts = url.split('github.com/')[-1]
            return parts.replace('.git', '').strip('/')
        elif 'git@github.com:' in url:
            parts = url.split('git@github.com:')[-1]
            return parts.replace('.git', '').strip('/')
    except Exception:
        pass

    return None


def _discover_pipx_tools() -> List[Tool]:
    """Discover tools installed via pipx."""
    tools = []

    try:
        result = subprocess.run(
            ['pipx', 'list', '--json'],
            capture_output=True, text=True
        )

        if result.returncode == 0:
            import json
            data = json.loads(result.stdout)

            for pkg_name, pkg_info in data.get('venvs', {}).items():
                metadata = pkg_info.get('metadata', {})
                main_pkg = metadata.get('main_package', {})
                app_paths = main_pkg.get('app_paths', [])

                tool = Tool(
                    name=pkg_name,
                    category='system',
                    install_method='pipx',
                    path=Path(app_paths[0]).parent if app_paths else Path.home() / '.local/bin',
                    pypi_name=pkg_name,
                )
                tools.append(tool)

    except Exception as e:
        logger.debug(f"Failed to discover pipx tools: {e}")

    return tools


def get_tools_for_update(tools: List[Tool], config) -> List[Tool]:
    """
    Filter tools based on configuration.

    Args:
        tools: List of all tools
        config: Configuration object

    Returns:
        Filtered list of tools to update
    """
    filtered = []

    for tool in tools:
        # Skip disabled tools
        if not tool.enabled:
            continue

        # Filter by category
        if config.category and tool.category != config.category:
            continue

        # Filter by specific tools
        if config.tools and tool.name not in config.tools:
            continue

        # Exclude specific tools
        if tool.name in config.exclude_tools:
            continue

        filtered.append(tool)

    return filtered


def get_updater_for_tool(tool: Tool, config):
    """
    Get the appropriate updater for a tool.

    Args:
        tool: Tool object
        config: Configuration object

    Returns:
        Updater instance
    """
    from ..updaters import (
        GitUpdater, GitPythonUpdater, FileReplacementUpdater,
        PipxUpdater, BinaryUpdater, AptUpdater, DockerUpdater, CustomUpdater
    )

    if tool.install_method == 'pipx':
        return PipxUpdater(tool, config)

    elif tool.install_method == 'binary':
        return BinaryUpdater(tool, config)

    elif tool.install_method == 'apt':
        return AptUpdater(tool, config)

    elif tool.install_method == 'docker':
        return DockerUpdater(tool, config)

    elif tool.install_method in ('git', 'git_python'):
        # Check if .git directory exists
        if (tool.path / '.git').exists():
            if tool.install_method == 'git_python':
                return GitPythonUpdater(tool, config)
            else:
                return GitUpdater(tool, config)
        else:
            # No .git - fall back to file replacement
            return FileReplacementUpdater(tool, config)

    elif tool.install_method == 'file_replacement':
        return FileReplacementUpdater(tool, config)

    elif tool.install_method == 'custom':
        return CustomUpdater(tool, config)

    else:
        raise ValueError(f"Unknown install method: {tool.install_method}")
