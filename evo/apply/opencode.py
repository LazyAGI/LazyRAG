from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from evo.apply.errors import ApplyError

log = logging.getLogger('evo.apply.opencode')


def _default_model() -> str | None:
    model = os.getenv('EVO_OPENCODE_MODEL') or os.getenv('OPENCODE_MODEL')
    provider = os.getenv('EVO_OPENCODE_PROVIDER') or os.getenv('OPENCODE_PROVIDER')
    if model and provider and '/' not in model:
        return f'{provider}/{model}'
    return model


@dataclass
class OpencodeOptions:
    binary: str | None = None
    model: str | None = _default_model()
    agent: str | None = None
    variant: str | None = None
    timeout_s: int = 600


@dataclass
class OpencodeOutcome:
    returncode: int
    text_summary: str
    last_error: dict | None
    events_path: Path
    stdout_path: Path
    stderr_path: Path


def resolve_binary(binary: str | None) -> str:
    candidate = (binary or os.getenv('OPENCODE_BIN') or shutil.which('opencode') or '').strip()
    if not candidate:
        raise ApplyError('OPENCODE_BIN_MISSING', 'opencode binary not found on PATH')
    return candidate


def default_auth_dir() -> Path:
    env = os.getenv('OPENCODE_DATA_DIR')
    if env:
        return Path(env)
    return Path.home() / '.local' / 'share' / 'opencode'


def preflight(binary: str | None, *, auth_dir: Path | None = None) -> str:
    resolved = resolve_binary(binary)
    auth = (auth_dir or default_auth_dir()) / 'auth.json'
    if not auth.is_file() or auth.stat().st_size == 0:
        raise ApplyError('OPENCODE_AUTH_MISSING',
                         'opencode auth.json missing or empty',
                         {'path': str(auth)})
    try:
        r = subprocess.run([resolved, '--version'], capture_output=True,
                           text=True, timeout=15, check=False)
    except FileNotFoundError as exc:
        raise ApplyError('OPENCODE_BIN_MISSING', 'opencode binary not executable',
                         {'binary': resolved}) from exc
    except subprocess.TimeoutExpired as exc:
        raise ApplyError('OPENCODE_BIN_MISSING', 'opencode --version timed out',
                         {'binary': resolved}) from exc
    if r.returncode != 0:
        raise ApplyError('OPENCODE_BIN_MISSING', 'opencode --version failed',
                         {'stderr': r.stderr[-500:]})
    return resolved


ProcSink = Callable[[subprocess.Popen], None]


def run_opencode(
    prompt: str,
    *,
    cwd: Path,
    artifact_dir: Path,
    binary: str,
    options: OpencodeOptions,
    on_proc: ProcSink | None = None,
) -> OpencodeOutcome:
    artifact_dir.mkdir(parents=True, exist_ok=True)

    cmd: list[str] = [binary, 'run', '--format', 'json']
    for flag, value in (('--model', options.model), ('--agent', options.agent),
                        ('--variant', options.variant)):
        if value:
            cmd.extend([flag, value])
    cmd.append(prompt)

    temp_config = _ensure_project_provider_config(cwd, options.model)
    env = dict(os.environ)
    api_key = _auth_api_key('deepseek')
    if api_key and (options.model or '').startswith('deepseek/'):
        env.setdefault('DEEPSEEK_API_KEY', api_key)

    log.info('opencode run: cwd=%s timeout_s=%d model=%s agent=%s variant=%s',
             cwd, options.timeout_s, options.model, options.agent, options.variant)
    proc = subprocess.Popen(cmd, cwd=str(cwd),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, env=env)
    if on_proc:
        on_proc(proc)
    try:
        stdout, stderr = proc.communicate(timeout=options.timeout_s)
    except subprocess.TimeoutExpired:
        _terminate(proc)
        _cleanup_temp_config(temp_config)
        raise ApplyError('OPENCODE_TIMEOUT', 'opencode run timed out',
                         {'timeout_s': options.timeout_s, 'cwd': str(cwd)})
    finally:
        _cleanup_temp_config(temp_config)

    stdout_path = artifact_dir / 'stdout.log'
    stderr_path = artifact_dir / 'stderr.log'
    events_path = artifact_dir / 'events.jsonl'
    summary_path = artifact_dir / 'text_summary.md'

    stdout_path.write_text(stdout or '', encoding='utf-8')
    stderr_path.write_text(stderr or '', encoding='utf-8')

    events, text_chunks, last_error = _parse_event_stream(stdout or '')
    events_path.write_text(
        ''.join(json.dumps(e, ensure_ascii=False) + '\n' for e in events),
        encoding='utf-8',
    )
    text_summary = '\n'.join(text_chunks).strip()
    summary_path.write_text(text_summary or '_(no text events)_\n', encoding='utf-8')

    return OpencodeOutcome(
        returncode=proc.returncode,
        text_summary=text_summary,
        last_error=last_error,
        events_path=events_path,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )


def _auth_api_key(provider: str) -> str | None:
    path = default_auth_dir() / 'auth.json'
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None
    entry = data.get(provider) if isinstance(data, dict) else None
    if isinstance(entry, dict) and isinstance(entry.get('key'), str):
        return entry['key']
    return None


def _ensure_project_provider_config(cwd: Path, model: str | None) -> Path | None:
    if not (model or '').startswith('deepseek/'):
        return None
    path = cwd / 'opencode.json'
    if path.exists():
        return None
    config = {
        '$schema': 'https://opencode.ai/config.json',
        'provider': {
            'deepseek': {
                'npm': '@ai-sdk/openai-compatible',
                'name': 'DeepSeek',
                'options': {
                    'baseURL': 'https://api.deepseek.com',
                    'apiKey': '{env:DEEPSEEK_API_KEY}',
                },
                'models': {
                    'deepseek-chat': {'name': 'DeepSeek Chat'},
                    'deepseek-v4-flash': {'name': 'DeepSeek V4 Flash'},
                    'deepseek-v4-pro': {'name': 'DeepSeek V4 Pro'},
                },
            },
        },
    }
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2),
                    encoding='utf-8')
    return path


def _cleanup_temp_config(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _terminate(proc: subprocess.Popen, grace_s: float = 5.0) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=grace_s)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(timeout=grace_s)
        except subprocess.TimeoutExpired:
            pass


def _parse_event_stream(raw: str) -> tuple[list[dict], list[str], dict | None]:
    events: list[dict] = []
    text_chunks: list[str] = []
    last_error: dict | None = None
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            obj: Any = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        events.append(obj)
        etype = obj.get('type')
        if etype == 'text':
            part = obj.get('part')
            if isinstance(part, dict):
                text = part.get('text')
                if isinstance(text, str) and text.strip():
                    text_chunks.append(text.strip())
        elif etype == 'error':
            last_error = obj
    return events, text_chunks, last_error
