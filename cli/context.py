"""Persistent CLI context: default dataset, algo config, etc.

Config is stored at ~/.lazyrag/config.json alongside credentials.
Resolution order: CLI flag > config file > env var > default/error.
"""

import json
import os
import sys
import tempfile
from typing import Any, Dict, Optional

from cli.config import CREDENTIALS_DIR

CONFIG_FILE = CREDENTIALS_DIR / 'config.json'

# Known config keys and their descriptions (for `config list`).
KNOWN_KEYS = {
    'dataset': 'Default dataset ID for most commands',
    'algo_url': 'Algo service URL for retrieve',
    'algo_dataset': 'Remote algo document name for retrieve',
}


# ---------------------------------------------------------------------------
# low-level read / write
# ---------------------------------------------------------------------------

def load_config() -> Dict[str, Any]:
    if not CONFIG_FILE.exists():
        return {}
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def save_config(data: Dict[str, Any]) -> None:
    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, indent=2, ensure_ascii=False) + '\n'
    # Atomic replace so concurrent CLI invocations can't leave a half-written
    # config.json on disk; the final os.replace is guaranteed atomic within a
    # filesystem, so either the full old file or the full new file is visible.
    fd, tmp_path = tempfile.mkstemp(
        dir=str(CREDENTIALS_DIR), prefix='.config_tmp',
    )
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            handle.write(content)
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, CONFIG_FILE)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def get(key: str) -> Optional[str]:
    return load_config().get(key)


def set_key(key: str, value: str) -> None:
    cfg = load_config()
    cfg[key] = value
    save_config(cfg)


def unset_key(key: str) -> None:
    cfg = load_config()
    cfg.pop(key, None)
    save_config(cfg)


# ---------------------------------------------------------------------------
# resolvers — CLI flag > config > env > default/error
# ---------------------------------------------------------------------------

def resolve_dataset(cli_value: Optional[str]) -> str:
    """Resolve dataset ID from CLI arg, config, or raise with hint."""
    if cli_value:
        return cli_value
    stored = get('dataset')
    if stored:
        return stored
    print(
        'Error: no dataset specified. '
        'Use --dataset <id> or run `lazyrag use <id>` to set a default.',
        file=sys.stderr,
    )
    sys.exit(1)


def resolve_algo_url(cli_value: Optional[str]) -> str:
    """Resolve algo service URL."""
    if cli_value:
        return cli_value.rstrip('/')
    stored = get('algo_url')
    if stored:
        return stored.rstrip('/')
    return os.getenv(
        'LAZYRAG_ALGO_SERVICE_URL', 'http://localhost:8000',
    ).rstrip('/')


def resolve_algo_dataset(cli_value: Optional[str]) -> str:
    """Resolve remote algo document name."""
    if cli_value:
        return cli_value
    stored = get('algo_dataset')
    if stored:
        return stored
    env = os.getenv('LAZYRAG_ALGO_DATASET_NAME')
    if env:
        return env
    return 'general_algo'
