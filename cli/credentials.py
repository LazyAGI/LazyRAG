"""Token persistence: save / load / clear credentials."""

import json
import time
from typing import Any, Dict, Optional

from cli.config import CREDENTIALS_DIR, CREDENTIALS_FILE


def _ensure_dir() -> None:
    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)


def save(data: Dict[str, Any]) -> None:
    """Persist login tokens to disk."""
    _ensure_dir()
    data['saved_at'] = time.time()
    CREDENTIALS_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding='utf-8',
    )
    CREDENTIALS_FILE.chmod(0o600)


def load() -> Optional[Dict[str, Any]]:
    """Return stored credentials or *None* if not logged in."""
    if not CREDENTIALS_FILE.exists():
        return None
    try:
        data = json.loads(CREDENTIALS_FILE.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict) or 'access_token' not in data:
        return None
    return data


def clear() -> None:
    """Remove stored credentials."""
    if CREDENTIALS_FILE.exists():
        CREDENTIALS_FILE.unlink()


def access_token() -> Optional[str]:
    """Return the current access token, or *None*."""
    creds = load()
    if creds is None:
        return None
    return creds.get('access_token')


def refresh_token() -> Optional[str]:
    """Return the current refresh token, or *None*."""
    creds = load()
    if creds is None:
        return None
    return creds.get('refresh_token')


def server_url() -> Optional[str]:
    """Return the server URL from stored credentials, or *None*."""
    creds = load()
    if creds is None:
        return None
    return creds.get('server_url')


def is_token_expired() -> bool:
    """Heuristic check: is the access token likely expired?"""
    creds = load()
    if creds is None:
        return True
    saved_at = creds.get('saved_at', 0)
    expires_in = creds.get('expires_in', 0)
    if not saved_at or not expires_in:
        return False  # can't tell, assume valid
    # consider expired 60s before actual expiry
    return time.time() > saved_at + expires_in - 60
