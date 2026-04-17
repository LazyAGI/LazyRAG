"""Token persistence: save / load / clear credentials."""

import json
import time
from typing import Any, Dict, Optional

from cli.config import CREDENTIALS_DIR, CREDENTIALS_FILE


def _ensure_dir() -> None:
    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
    # Credentials are per-user secrets; tighten dir permissions so
    # other users on multi-tenant hosts can't enumerate our tokens.
    try:
        CREDENTIALS_DIR.chmod(0o700)
    except OSError:
        pass


def save(data: Dict[str, Any]) -> None:
    """Persist login tokens to disk."""
    _ensure_dir()
    # Copy so we don't mutate the caller's dict with our bookkeeping field.
    to_write = {**data, 'saved_at': time.time()}
    # Create with 0600 *before* writing to avoid the TOCTOU window between
    # write_text and chmod where another process could read the token.
    if not CREDENTIALS_FILE.exists():
        import os
        fd = os.open(
            str(CREDENTIALS_FILE),
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            0o600,
        )
        os.close(fd)
    CREDENTIALS_FILE.chmod(0o600)
    CREDENTIALS_FILE.write_text(
        json.dumps(to_write, indent=2, ensure_ascii=False),
        encoding='utf-8',
    )


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
    CREDENTIALS_FILE.unlink(missing_ok=True)


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
