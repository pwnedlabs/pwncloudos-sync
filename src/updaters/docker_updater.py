"""
Docker image updater for pwncloudos-sync.

Handles Docker Compose v2 (Debian 12 default: `docker compose` plugin)
with fallback to v1 (`docker-compose` standalone).
"""

import shutil
import subprocess
from typing import List, Optional
from .base import BaseUpdater, UpdateResult


class DockerUpdater(BaseUpdater):
    """Updater for Docker-based tools."""

    def _compose_command(self) -> Optional[List[str]]:
        """Detect available compose command — prefer v2 plugin, fall back to v1."""
        # Try Docker Compose v2 plugin first (Debian 12 default)
        try:
            result = subprocess.run(
                ['docker', 'compose', 'version'],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                return ['docker', 'compose']
        except Exception:
            pass

        # Fall back to docker-compose v1
        if shutil.which('docker-compose'):
            return ['docker-compose']

        return None

    def _docker_available(self) -> Optional[str]:
        """Check if Docker daemon is running and accessible. Returns error string or None."""
        try:
            result = subprocess.run(
                ['docker', 'info'],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0:
                stderr = result.stderr.lower()
                if 'permission denied' in stderr:
                    return "Docker permission denied — user may need to be in 'docker' group"
                if 'cannot connect' in stderr or 'is the docker daemon running' in stderr:
                    return "Docker daemon is not running"
                return f"Docker error: {result.stderr.strip()[:100]}"
        except FileNotFoundError:
            return "Docker is not installed"
        except subprocess.TimeoutExpired:
            return "Docker daemon not responding (timeout)"
        except Exception as e:
            return f"Docker check failed: {e}"
        return None

    def get_current_version(self) -> Optional[str]:
        """Get current image version."""
        return None

    def get_latest_version(self) -> Optional[str]:
        """Get latest version (not applicable for Docker)."""
        return None

    def needs_update(self) -> bool:
        """Docker images should always be checked for updates."""
        return True

    def perform_update(self) -> UpdateResult:
        """Execute docker compose pull."""
        # Pre-flight: check Docker daemon
        docker_error = self._docker_available()
        if docker_error:
            return UpdateResult(
                success=False,
                tool_name=self.tool.name,
                error_message=docker_error,
            )

        try:
            compose_file = getattr(self.tool, 'docker_compose', None)

            if compose_file:
                compose_cmd = self._compose_command()
                if not compose_cmd:
                    return UpdateResult(
                        success=False,
                        tool_name=self.tool.name,
                        error_message="Neither 'docker compose' (v2) nor 'docker-compose' (v1) found",
                    )

                result = subprocess.run(
                    compose_cmd + ['-f', str(compose_file), 'pull'],
                    capture_output=True, text=True, timeout=600
                )
            else:
                # Try docker pull directly
                result = subprocess.run(
                    ['docker', 'pull', self.tool.name],
                    capture_output=True, text=True, timeout=600
                )

            if result.returncode == 0:
                return UpdateResult(
                    success=True,
                    tool_name=self.tool.name,
                    old_version="docker",
                    new_version="latest",
                )
            else:
                return UpdateResult(
                    success=False,
                    tool_name=self.tool.name,
                    error_message=result.stderr,
                )

        except subprocess.TimeoutExpired:
            return UpdateResult(
                success=False,
                tool_name=self.tool.name,
                error_message="Docker pull timed out",
            )
        except Exception as e:
            return UpdateResult(
                success=False,
                tool_name=self.tool.name,
                error_message=str(e),
            )
