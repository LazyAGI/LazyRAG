from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evo.apply.errors import ApplyError


_CREDENTIALS_RE = re.compile(r'(\d+)\s+credentials')

log = logging.getLogger('evo.apply.opencode')


@dataclass
class OpencodeOptions:
    binary: str | None = None
    model: str | None = None
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


def preflight(binary: str | None) -> str:
    resolved = resolve_binary(binary)
    try:
        result = subprocess.run(
            [resolved, 'auth', 'list'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=30, check=False,
        )
    except FileNotFoundError as exc:
        raise ApplyError('OPENCODE_BIN_MISSING', 'opencode binary not executable',
                         {'binary': resolved}) from exc
    except subprocess.TimeoutExpired as exc:
        raise ApplyError('OPENCODE_AUTH_MISSING', 'opencode auth list timed out',
                         {'binary': resolved}) from exc

    combined = '\n'.join(p for p in (result.stdout, result.stderr) if p)
    if result.returncode != 0:
        raise ApplyError('OPENCODE_AUTH_MISSING', 'opencode auth list failed',
                         {'stdout': result.stdout, 'stderr': result.stderr})
    match = _CREDENTIALS_RE.search(combined)
    if not match or int(match.group(1)) < 1:
        raise ApplyError('OPENCODE_AUTH_MISSING', 'opencode has no configured credentials',
                         {'output': combined})
    return resolved


def run_opencode(
    prompt: str,
    *,
    cwd: Path,
    artifact_dir: Path,
    binary: str,
    options: OpencodeOptions,
) -> OpencodeOutcome:
    artifact_dir.mkdir(parents=True, exist_ok=True)

    cmd: list[str] = [binary, 'run', '--format', 'json']
    for flag, value in (('--model', options.model), ('--agent', options.agent),
                        ('--variant', options.variant)):
        if value:
            cmd.extend([flag, value])
    cmd.append(prompt)

    log.info('opencode run: cwd=%s timeout_s=%d model=%s agent=%s variant=%s',
             cwd, options.timeout_s, options.model, options.agent, options.variant)
    try:
        proc = subprocess.run(
            cmd, cwd=str(cwd),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=options.timeout_s, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ApplyError('OPENCODE_TIMEOUT', 'opencode run timed out',
                         {'timeout_s': options.timeout_s, 'cwd': str(cwd)}) from exc

    stdout_path = artifact_dir / 'stdout.log'
    stderr_path = artifact_dir / 'stderr.log'
    events_path = artifact_dir / 'events.jsonl'
    summary_path = artifact_dir / 'text_summary.md'

    stdout_path.write_text(proc.stdout or '', encoding='utf-8')
    stderr_path.write_text(proc.stderr or '', encoding='utf-8')

    events, text_chunks, last_error = _parse_event_stream(proc.stdout or '')
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
