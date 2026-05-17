"""CLI configuration: default URLs and credential paths."""

import os
from pathlib import Path

DEFAULT_SERVER_URL = os.getenv('LAZYMIND_SERVER_URL', 'http://localhost:8000')

# Empty string for LAZYMIND_HOME falls back to the default rather than the
# cwd, so users who export an unset variable don't silently scatter state.
_LAZYMIND_HOME = os.getenv('LAZYMIND_HOME') or '~/.lazymind'
CREDENTIALS_DIR = Path(_LAZYMIND_HOME).expanduser()
CREDENTIALS_FILE = CREDENTIALS_DIR / 'credentials.json'

# API path prefixes (routed through Kong gateway)
AUTH_API_PREFIX = '/api/authservice/auth'
CORE_API_PREFIX = '/api/core'
