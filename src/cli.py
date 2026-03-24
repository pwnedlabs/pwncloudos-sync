"""
CLI argument parsing and interactive display for pwncloudos-sync.
"""

import argparse
import shlex
import shutil
import subprocess
import re
import json
from pathlib import Path
from typing import List, Optional


def create_parser() -> argparse.ArgumentParser:
    """Create CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog='pwncloudos-sync',
        description='Update all PwnCloudOS security tools to their latest versions',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  pwncloudos-sync --list              # Show all tools with location and version
  pwncloudos-sync --check             # Check for available updates
  pwncloudos-sync --all               # Update all tools (with confirmation)
  pwncloudos-sync --all -y            # Update all tools (skip confirmation)
  pwncloudos-sync --category aws      # Update only AWS tools
  pwncloudos-sync --tool cloudfox     # Update specific tool
  pwncloudos-sync --dry-run           # Show what would be updated
        """
    )

    # Update scope
    scope = parser.add_argument_group('Update Scope')
    scope.add_argument('--all', '-a', action='store_true',
                       help='Update all tools (will show summary and ask for confirmation)')
    scope.add_argument('--category', '-c',
                       choices=['aws', 'azure', 'gcp', 'multi_cloud',
                               'ps_tools', 'code_scanning', 'cracking', 'system'],
                       help='Update only tools in specific category')
    scope.add_argument('--tool', '-t', action='append', dest='tools',
                       help='Update specific tool(s) by name')
    scope.add_argument('--exclude', '-e', action='append', dest='exclude_tools',
                       default=[],
                       help='Exclude specific tool(s) from update')

    # Information
    info = parser.add_argument_group('Information')
    info.add_argument('--list', '-l', action='store_true', dest='list_only',
                      help='List all tools with location and version (no changes made)')
    info.add_argument('--check', action='store_true', dest='check_only',
                      help='Check for updates without installing')

    # Behavior
    behavior = parser.add_argument_group('Behavior')
    behavior.add_argument('--dry-run', '-n', action='store_true',
                          help='Show what would be updated without making changes')
    behavior.add_argument('--force', '-f', action='store_true',
                          help='Force update even if already at latest version')
    behavior.add_argument('--yes', '-y', action='store_true', dest='no_confirm',
                          help='Skip confirmation prompt (use with caution)')
    behavior.add_argument('--no-rollback', action='store_true',
                          help='Disable automatic rollback on failure')
    behavior.add_argument('--parallel', '-p', action='store_true',
                          help='Update tools in parallel (faster)')
    behavior.add_argument('--workers', type=int, default=4,
                          help='Number of parallel workers (default: 4)')

    # Output
    output = parser.add_argument_group('Output')
    output.add_argument('--verbose', '-v', action='count', default=0,
                        help='Increase verbosity (-v, -vv, -vvv)')
    output.add_argument('--quiet', '-q', action='store_true',
                        help='Suppress all output except errors')
    output.add_argument('--log-file', type=Path,
                        default=Path('logs/pwncloudos-sync.log'),
                        help='Log file path')
    output.add_argument('--json', action='store_true',
                        help='Output results as JSON')

    info.add_argument('--version', action='version',
                      version='%(prog)s 1.0.0')

    return parser


def parse_args(args=None):
    """Parse command line arguments."""
    parser = create_parser()
    return parser.parse_args(args)


# ============================================================================
# ANSI Color Codes
# ============================================================================

class Colors:
    """ANSI color codes for terminal output."""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'
    GRAY = '\033[90m'
    WHITE = '\033[97m'
    MAGENTA = '\033[35m'
    LIGHT_BLUE = '\033[38;5;75m'
    ORANGE = '\033[38;5;208m'
    TEAL = '\033[38;5;80m'
    PINK = '\033[38;5;213m'
    LIME = '\033[38;5;154m'
    LAVENDER = '\033[38;5;141m'
    SALMON = '\033[38;5;210m'
    SKY = '\033[38;5;117m'

    # Per-category color map
    CATEGORY_COLORS = {
        'aws': '\033[38;5;208m',      # Orange
        'azure': '\033[38;5;75m',     # Light blue
        'gcp': '\033[38;5;80m',       # Teal
        'multi_cloud': '\033[38;5;141m',  # Lavender
        'ps_tools': '\033[38;5;213m',     # Pink
        'code_scanning': '\033[38;5;154m', # Lime
        'cracking': '\033[38;5;210m',     # Salmon
        'system': '\033[38;5;117m',       # Sky blue
    }

    @classmethod
    def category(cls, cat: str) -> str:
        """Return colored category string."""
        color = cls.CATEGORY_COLORS.get(cat, cls.GRAY)
        return f"{color}{cat}{cls.END}"


# ============================================================================
# Banner Display
# ============================================================================

def print_banner():
    """Print the pwncloudos-sync banner."""
    banner = f"""
{Colors.CYAN}╔══════════════════════════════════════════════════════════════════════════════════════════╗
║                                                                                          ║
║  {Colors.MAGENTA}██████╗ ██╗    ██╗███╗   ██╗ ██████╗██╗      ██████╗ ██╗   ██╗██████╗  ██████╗ ███████╗{Colors.CYAN} ║
║  {Colors.MAGENTA}██╔══██╗██║    ██║████╗  ██║██╔════╝██║     ██╔═══██╗██║   ██║██╔══██╗██╔═══██╗██╔════╝{Colors.CYAN} ║
║  {Colors.MAGENTA}██████╔╝██║ █╗ ██║██╔██╗ ██║██║     ██║     ██║   ██║██║   ██║██║  ██║██║   ██║███████╗{Colors.CYAN} ║
║  {Colors.MAGENTA}██╔═══╝ ██║███╗██║██║╚██╗██║██║     ██║     ██║   ██║██║   ██║██║  ██║██║   ██║╚════██║{Colors.CYAN} ║
║  {Colors.MAGENTA}██║     ╚███╔███╔╝██║ ╚████║╚██████╗███████╗╚██████╔╝╚██████╔╝██████╔╝╚██████╔╝███████║{Colors.CYAN} ║
║  {Colors.MAGENTA}╚═╝      ╚══╝╚══╝ ╚═╝  ╚═══╝ ╚═════╝╚══════╝ ╚═════╝  ╚═════╝ ╚═════╝  ╚═════╝ ╚══════╝{Colors.CYAN} ║
║                                                                                          ║
║                {Colors.YELLOW}PWNCLOUDOS{Colors.CYAN} - Security Tool Updater v1.0.0                              ║
║                          {Colors.WHITE}https://pwncloudos.pwnedlabs.io{Colors.CYAN}                              ║
║                                                                                          ║
╚══════════════════════════════════════════════════════════════════════════════════════════╝{Colors.END}
"""
    print(banner)


# ============================================================================
# PowerShell Version Detection
# ============================================================================

_pwsh_available: Optional[bool] = None


def check_pwsh_available() -> bool:
    """Check if PowerShell (pwsh) is installed and working."""
    global _pwsh_available
    if _pwsh_available is not None:
        return _pwsh_available
    try:
        result = subprocess.run(
            ['pwsh', '--version'],
            capture_output=True, text=True, timeout=10
        )
        _pwsh_available = result.returncode == 0
    except Exception:
        _pwsh_available = False
    return _pwsh_available


def _get_ps_module_version(tool) -> Optional[str]:
    """
    Extract version from a PowerShell module manifest (.psd1) using pwsh.

    Falls back to None if pwsh is not available or the manifest is missing.
    """
    if not check_pwsh_available():
        return None

    manifest_name = tool.ps_module_manifest
    manifest_path = Path(tool.path) / manifest_name

    if not manifest_path.exists():
        # Try to find it recursively
        candidates = list(Path(tool.path).rglob(manifest_name))
        if candidates:
            manifest_path = candidates[0]
        else:
            return None

    try:
        cmd = f"(Import-PowerShellDataFile '{manifest_path}').ModuleVersion"
        result = subprocess.run(
            ['pwsh', '-NoProfile', '-Command', cmd],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass

    return None


# ============================================================================
# Version Detection
# ============================================================================

def get_tool_version(tool) -> str:
    """Get the current version of a tool."""

    # PowerShell module manifest (.psd1) — dedicated detection path
    if getattr(tool, 'ps_module_manifest', None):
        version = _get_ps_module_version(tool)
        if version:
            return version
        # Fall through to git hash fallback

    # Try explicit version command if available
    if tool.version_command:
        try:
            result = subprocess.run(
                shlex.split(tool.version_command),
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 or result.stdout or result.stderr:
                output = result.stdout + result.stderr
                match = re.search(r'v?(\d+\.\d+\.?\d*)', output)
                if match:
                    return match.group(1)
        except Exception:
            pass

    # For git repos, get short commit hash
    if tool.path.is_dir():
        git_dir = tool.path / '.git'
        if git_dir.exists():
            try:
                # Ensure safe.directory is configured for /opt/ paths
                tool_path_str = str(tool.path)
                safe_check = subprocess.run(
                    ['git', 'config', '--global', '--get-all', 'safe.directory'],
                    capture_output=True, text=True, timeout=5
                )
                configured = safe_check.stdout.strip().splitlines() if safe_check.returncode == 0 else []
                if tool_path_str not in configured and '*' not in configured:
                    subprocess.run(
                        ['git', 'config', '--global', '--add', 'safe.directory', tool_path_str],
                        capture_output=True, text=True, timeout=5
                    )
                result = subprocess.run(
                    ['git', '-C', tool_path_str, 'rev-parse', '--short', 'HEAD'],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    return f"git:{result.stdout.strip()}"
            except Exception:
                pass

    # For pipx tools
    if tool.install_method == 'pipx' and tool.pypi_name:
        try:
            result = subprocess.run(
                ['pipx', 'list', '--json'],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                venv = data.get('venvs', {}).get(tool.pypi_name, {})
                ver = venv.get('metadata', {}).get('main_package', {}).get('version')
                if ver:
                    return ver
        except Exception:
            pass

    return "N/A"


def check_tool_exists(tool) -> bool:
    """Check if tool exists at the specified path."""
    if tool.path.exists():
        return True

    # For pipx tools, check if command exists
    if tool.install_method == 'pipx':
        try:
            names_to_try = [tool.name, tool.path.name]
            for candidate in names_to_try:
                if not candidate:
                    continue
                if shutil.which(candidate):
                    return True
        except Exception:
            pass

    return False


# ============================================================================
# Table Display
# ============================================================================

def print_tools_table(tools: List):
    """
    Print all tools in a formatted table.
    Shows: #, Tool Name, Category, Method, Version, Status, Path
    """
    if not tools:
        print(f"\n{Colors.YELLOW}No tools found.{Colors.END}\n")
        return

    # Column widths
    name_w = max(len(t.name) for t in tools) + 2
    name_w = max(name_w, 25)
    cat_w = 14
    method_w = 18
    ver_w = 15
    status_w = 12
    path_w = 50

    # Table header
    header_line = "═" * (5 + name_w + cat_w + method_w + ver_w + status_w + path_w)

    print(f"\n{Colors.CYAN}{header_line}{Colors.END}")
    print(
        f"{Colors.BOLD}{Colors.WHITE}"
        f"{'#':<5}"
        f"{'TOOL NAME':<{name_w}}"
        f"{'CATEGORY':<{cat_w}}"
        f"{'METHOD':<{method_w}}"
        f"{'VERSION':<{ver_w}}"
        f"{'STATUS':<{status_w}}"
        f"{'PATH':<{path_w}}"
        f"{Colors.END}"
    )
    print(f"{Colors.CYAN}{header_line}{Colors.END}")

    # Group by category
    categories = {}
    for tool in tools:
        if tool.category not in categories:
            categories[tool.category] = []
        categories[tool.category].append(tool)

    # Method colors
    method_colors = {
        'git': Colors.BLUE,
        'git_python': Colors.BLUE,
        'file_replacement': Colors.CYAN,
        'pipx': Colors.GREEN,
        'binary': Colors.YELLOW,
        'apt': Colors.GRAY,
        'docker': Colors.MAGENTA,
        'custom': Colors.YELLOW,
    }

    idx = 1
    for category in sorted(categories.keys()):
        # Category header
        print(f"\n{Colors.YELLOW}{Colors.BOLD}  ▶ {category.upper()}{Colors.END}")
        print(f"{Colors.GRAY}  {'─' * (header_line.__len__() - 4)}{Colors.END}")

        for tool in sorted(categories[category], key=lambda t: t.name.lower()):
            exists = check_tool_exists(tool)
            version = get_tool_version(tool) if exists else "NOT FOUND"

            # Status
            if not exists:
                status = f"{Colors.RED}✗ Missing{Colors.END}"
                status_plain = "Missing"
            else:
                status = f"{Colors.GREEN}✓ OK{Colors.END}"
                status_plain = "OK"

            # Method with color
            method_color = method_colors.get(tool.install_method, Colors.WHITE)
            method_display = f"{method_color}{tool.install_method}{Colors.END}"

            # Truncate path if needed
            path_str = str(tool.path)
            if len(path_str) > path_w - 3:
                path_str = "..." + path_str[-(path_w - 6):]

            # Version color (gray if N/A)
            if version == "N/A" or version == "NOT FOUND":
                ver_display = f"{Colors.GRAY}{version}{Colors.END}"
            else:
                ver_display = f"{Colors.WHITE}{version}{Colors.END}"

            print(
                f"  {Colors.CYAN}{idx:<4}{Colors.END}"
                f"{Colors.WHITE}{tool.name:<{name_w}}{Colors.END}"
                f"{Colors.GRAY}{tool.category:<{cat_w}}{Colors.END}"
                f"{method_display:<{method_w + 9}}"  # +9 for ANSI codes
                f"{ver_display:<{ver_w + 9}}"
                f"{status:<{status_w + 9}}"
                f"{Colors.GRAY}{path_str}{Colors.END}"
            )
            idx += 1

    # Footer
    print(f"\n{Colors.CYAN}{header_line}{Colors.END}")

    # Summary counts
    total = len(tools)
    ok = sum(1 for t in tools if check_tool_exists(t))
    missing = total - ok

    print(f"\n{Colors.BOLD}Summary:{Colors.END}")
    print(f"  • Total tools: {Colors.WHITE}{total}{Colors.END}")
    print(f"  • {Colors.GREEN}Available: {ok}{Colors.END}")
    if missing > 0:
        print(f"  • {Colors.RED}Missing: {missing}{Colors.END}")

    # Count by method
    methods = {}
    for t in tools:
        methods[t.install_method] = methods.get(t.install_method, 0) + 1

    print(f"\n{Colors.BOLD}By update method:{Colors.END}")
    for method, count in sorted(methods.items()):
        color = method_colors.get(method, Colors.WHITE)
        print(f"  • {color}{method}{Colors.END}: {count}")

    print()


# ============================================================================
# Update Summary & Confirmation
# ============================================================================

def print_update_summary(tools: List):
    """Print summary before performing updates."""

    print(f"\n{Colors.YELLOW}{'═' * 70}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.YELLOW}                         UPDATE SUMMARY{Colors.END}")
    print(f"{Colors.YELLOW}{'═' * 70}{Colors.END}\n")

    # Count by category
    categories = {}
    for tool in tools:
        categories[tool.category] = categories.get(tool.category, 0) + 1

    print(f"{Colors.BOLD}Tools to update by category:{Colors.END}")
    for cat, count in sorted(categories.items()):
        print(f"  • {cat}: {Colors.CYAN}{count}{Colors.END} tools")

    # Count by method
    methods = {}
    for tool in tools:
        methods[tool.install_method] = methods.get(tool.install_method, 0) + 1

    print(f"\n{Colors.BOLD}Update methods to be used:{Colors.END}")
    for method, count in sorted(methods.items()):
        print(f"  • {method}: {Colors.CYAN}{count}{Colors.END} tools")

    print(f"\n{Colors.BOLD}Total: {Colors.CYAN}{len(tools)}{Colors.END} tools will be checked for updates")
    print(f"{Colors.YELLOW}{'─' * 70}{Colors.END}")


def confirm_update() -> bool:
    """Ask user to confirm the update."""
    print(f"\n{Colors.YELLOW}{Colors.BOLD}⚠️  WARNING:{Colors.END}")
    print(f"   This will update the tools listed above.")
    print(f"   • Backups will be created before each update")
    print(f"   • Failed updates will be automatically rolled back")
    print(f"   • Launcher scripts will NOT be modified\n")

    try:
        response = input(f"{Colors.BOLD}Do you want to proceed? [y/N]: {Colors.END}").strip().lower()
        return response in ('y', 'yes')
    except (KeyboardInterrupt, EOFError):
        print("\n")
        return False


# ============================================================================
# Check Updates Display
# ============================================================================

def print_update_check_results(tools: List, results: dict):
    """Print results of update check."""

    print(f"\n{Colors.CYAN}{'═' * 80}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.WHITE}                           UPDATE CHECK RESULTS{Colors.END}")
    print(f"{Colors.CYAN}{'═' * 80}{Colors.END}\n")

    updates_available = []
    up_to_date = []
    errors = []

    for tool in tools:
        result = results.get(tool.name, {})
        if result.get('error'):
            errors.append((tool, result['error']))
        elif result.get('needs_update'):
            updates_available.append((tool, result.get('current'), result.get('latest')))
        else:
            up_to_date.append(tool)

    # Updates available
    if updates_available:
        print(f"{Colors.YELLOW}{Colors.BOLD}Updates Available ({len(updates_available)}):{Colors.END}")
        for tool, current, latest in updates_available:
            print(f"  {Colors.YELLOW}↑{Colors.END} {tool.name}: {current or 'unknown'} → {Colors.GREEN}{latest or 'new'}{Colors.END}")

    # Up to date
    if up_to_date:
        print(f"\n{Colors.GREEN}{Colors.BOLD}Already Up to Date ({len(up_to_date)}):{Colors.END}")
        for tool in up_to_date:
            print(f"  {Colors.GREEN}✓{Colors.END} {tool.name}")

    # Errors
    if errors:
        print(f"\n{Colors.RED}{Colors.BOLD}Check Failed ({len(errors)}):{Colors.END}")
        for tool, error in errors:
            print(f"  {Colors.RED}✗{Colors.END} {tool.name}: {error}")

    print(f"\n{Colors.CYAN}{'═' * 80}{Colors.END}\n")
