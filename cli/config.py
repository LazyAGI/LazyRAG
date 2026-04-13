"""CLI configuration: default URLs and credential paths."""

import os
from pathlib import Path

DEFAULT_SERVER_URL = os.getenv('LAZYRAG_SERVER_URL', 'http://localhost:8000')

CREDENTIALS_DIR = Path(os.getenv('LAZYRAG_HOME', '~/.lazyrag')).expanduser()
CREDENTIALS_FILE = CREDENTIALS_DIR / 'credentials.json'

# API path prefixes (routed through Kong gateway)
AUTH_API_PREFIX = '/api/authservice/auth'
CORE_API_PREFIX = '/api/core'
