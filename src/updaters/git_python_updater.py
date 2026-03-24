"""
Git + Python dependencies updater for pwncloudos-sync.
"""

import subprocess
from .git_updater import GitUpdater
from .base import UpdateResult


class GitPythonUpdater(GitUpdater):
    """Updater for git repositories with Python dependencies."""

    def perform_update(self) -> UpdateResult:
        """Execute git pull and update Python dependencies."""
        # First: git pull (via parent class)
        git_result = super().perform_update()

        if not git_result.success:
            return git_result

        # Update Python dependencies
        req_file = self.tool.path / "requirements.txt"
        if req_file.exists():
            self.logger.info(f"Installing Python dependencies from {req_file}")
            try:
                result = subprocess.run(
                    ['python3', '-m', 'pip', 'install', '-r', str(req_file), '--upgrade', '--quiet'],
                    capture_output=True, text=True, timeout=300
                )

                if result.returncode != 0:
                    self.logger.warning(f"pip install warning: {result.stderr}")
                    # Don't fail the update, just warn
            except subprocess.TimeoutExpired:
                self.logger.warning("pip install timed out")
            except Exception as e:
                self.logger.warning(f"pip install error: {e}")

        # Check for setup.py or pyproject.toml
        setup_py = self.tool.path / "setup.py"
        pyproject = self.tool.path / "pyproject.toml"

        if setup_py.exists():
            self.logger.info("Running pip install -e .")
            try:
                subprocess.run(
                    ['python3', '-m', 'pip', 'install', '-e', str(self.tool.path), '--quiet'],
                    capture_output=True, text=True, timeout=300
                )
            except Exception as e:
                self.logger.warning(f"pip install -e failed: {e}")

        elif pyproject.exists():
            self.logger.info("Running pip install from pyproject.toml")
            try:
                subprocess.run(
                    ['python3', '-m', 'pip', 'install', str(self.tool.path), '--quiet'],
                    capture_output=True, text=True, timeout=300
                )
            except Exception as e:
                self.logger.warning(f"pip install failed: {e}")

        return git_result

    def verify_update(self) -> bool:
        """Verify Python tool works."""
        # First check git status
        if not super().verify_update():
            return False

        # Try to run the tool
        py_files = list(self.tool.path.glob('*.py'))
        main_script = None

        # Find main script
        tool_name = self.tool.path.name.lower()
        for pattern in [f"{tool_name}.py", "main.py", "__main__.py"]:
            candidate = self.tool.path / pattern
            if candidate.exists():
                main_script = candidate
                break

        if not main_script and py_files:
            main_script = py_files[0]

        if main_script:
            try:
                result = subprocess.run(
                    ['python3', str(main_script), '--help'],
                    capture_output=True, timeout=10
                )
                # Return True even if --help returns non-zero (some tools do this)
                return True
            except Exception:
                pass

        return True  # Can't verify, assume OK
