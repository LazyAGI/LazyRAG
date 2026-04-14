from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from automation.opencode_adapter.errors import AdapterError, OPENCODE_EXEC_FAILED


def parse_event_stream(raw_output: str) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    for index, line in enumerate(raw_output.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise AdapterError(
                OPENCODE_EXEC_FAILED,
                'opencode produced non-JSON output',
                {'line_number': index, 'line': line, 'error': str(exc)},
            ) from exc
        if not isinstance(parsed, dict):
            raise AdapterError(
                OPENCODE_EXEC_FAILED,
                'opencode produced a non-object JSON event',
                {'line_number': index, 'event': parsed},
            )
        events.append(parsed)
    return events


def extract_text(events: List[Dict[str, Any]]) -> str:
    chunks: List[str] = []
    for event in events:
        if event.get('type') != 'text':
            continue
        part = event.get('part')
        if not isinstance(part, dict):
            continue
        text = part.get('text')
        if isinstance(text, str) and text.strip():
            chunks.append(text.strip())
    return '\n'.join(chunks).strip()


def extract_error_event(events: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    last_error: Optional[Dict[str, Any]] = None
    for event in events:
        if event.get('type') == 'error':
            last_error = event
    return last_error
