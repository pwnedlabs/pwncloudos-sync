"""
Network connectivity checks for pwncloudos-sync.
"""

import subprocess
import requests
from typing import Dict, Optional
import logging

logger = logging.getLogger('pwncloudos-sync')

# Test endpoints for connectivity
TEST_ENDPOINTS = [
    'https://api.github.com',
    'https://pypi.org',
    'https://deb.debian.org',
]


def check_internet_connectivity(timeout: int = 5) -> bool:
    """
    Check if internet connectivity is available.

    Args:
        timeout: Timeout in seconds for each endpoint

    Returns:
        bool: True if at least one endpoint is reachable
    """
    for endpoint in TEST_ENDPOINTS:
        try:
            response = requests.head(endpoint, timeout=timeout)
            if response.status_code < 400:
                logger.debug(f"Connectivity check passed: {endpoint}")
                return True
        except requests.RequestException as e:
            logger.debug(f"Connectivity check failed for {endpoint}: {e}")
            continue

    return False


def check_github_api_rate_limit() -> Optional[Dict]:
    """
    Check GitHub API rate limit.

    Returns:
        Dict with 'limit', 'remaining', 'reset' keys, or None on error
    """
    try:
        response = requests.get(
            'https://api.github.com/rate_limit',
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            core = data.get('resources', {}).get('core', {})
            return {
                'limit': core.get('limit', 60),
                'remaining': core.get('remaining', 60),
                'reset': core.get('reset', 0),
            }
    except requests.RequestException as e:
        logger.warning(f"Failed to check GitHub rate limit: {e}")

    return None


def test_source_connectivity(source: str, timeout: int = 10) -> Dict:
    """
    Test connectivity to a specific source.

    Args:
        source: URL to test (GitHub repo URL, PyPI package URL, etc.)
        timeout: Timeout in seconds

    Returns:
        Dict with 'available', 'latency_ms', 'error' keys
    """
    import time

    result = {
        'available': False,
        'latency_ms': None,
        'error': None,
    }

    try:
        start = time.time()
        response = requests.head(source, timeout=timeout, allow_redirects=True)
        latency = (time.time() - start) * 1000

        result['available'] = response.status_code < 400
        result['latency_ms'] = round(latency, 2)

    except requests.RequestException as e:
        result['error'] = str(e)

    return result


def get_github_repo_info(repo: str) -> Optional[Dict]:
    """
    Get information about a GitHub repository.

    Args:
        repo: Repository in 'owner/repo' format

    Returns:
        Dict with repo info, or None on error
    """
    try:
        response = requests.get(
            f'https://api.github.com/repos/{repo}',
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            return {
                'default_branch': data.get('default_branch', 'main'),
                'updated_at': data.get('updated_at'),
                'pushed_at': data.get('pushed_at'),
                'description': data.get('description'),
            }
    except requests.RequestException as e:
        logger.debug(f"Failed to get repo info for {repo}: {e}")

    return None
