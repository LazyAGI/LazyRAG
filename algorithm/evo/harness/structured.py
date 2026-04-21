from __future__ import annotations

import json
from typing import Callable

import json_repair
from jsonschema import Draft202012Validator

from evo.harness.react import LLMInvoker
from evo.runtime.session import AnalysisSession
from evo.utils import strip_thinking

_ERROR_LIMIT = 20
_PREVIEW_CHARS = 4000


def _format_error(err) -> str:
    path = '.'.join(str(p) for p in err.absolute_path) or '<root>'
    return f'{path}: {err.message}'


def _parse(raw: str) -> tuple[dict, bool]:
    text = strip_thinking(raw or '').strip()
    if not text:
        return {}, False
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj, False
    except json.JSONDecodeError:
        pass
    try:
        obj = json_repair.loads(text)
    except Exception:
        obj = None
    return (obj if isinstance(obj, dict) else {}), True


def parse_and_validate(raw: str, schema: dict) -> tuple[dict, list[str], bool]:
    data, repaired = _parse(raw)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    return data, [_format_error(e) for e in errors], repaired


def _repair_user(original_user: str, raw: str, errors: list[str]) -> str:
    joined = '\n'.join(f'- {e}' for e in errors[:_ERROR_LIMIT])
    preview = (raw or '')[:_PREVIEW_CHARS]
    return (
        f'{original_user}\n\n---\n\n'
        'Your previous output failed JSON Schema validation.\n'
        f'Previous output:\n{preview}\n\n'
        f'Validation errors:\n{joined}\n\n'
        'Return a CORRECTED JSON object only. '
        'No markdown fences, no reasoning text, all required fields present.'
    )


def _dump_raw(session: AnalysisSession, agent: str, raw: str) -> str | None:
    if not raw:
        return None
    try:
        path = (session.config.output_dir / 'runs' / session.run_id
                / 'raw' / f"{agent.replace(':', '_')}.txt")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(raw, encoding='utf-8')
        return str(path)
    except OSError:
        return None


def invoke_structured(session: AnalysisSession, invoker: LLMInvoker, user_text: str,
                      *, agent: str, schema: dict, cache_key: str | None = None,
                      max_repair: int = 1, producer: Callable[[str], str] | None = None,
                      ) -> dict:
    current_user = user_text
    parsed: dict = {}
    errors: list[str] = []
    raw_last = ''
    for attempt in range(max_repair + 1):
        agent_tag = agent if attempt == 0 else f'{agent}:repair{attempt}'
        call_user = current_user
        if attempt == 0 and producer is not None:
            fn = producer
            raw = session.llm.call(
                producer=lambda: fn(call_user),
                cache_key=cache_key,
                use_cache=cache_key is not None,
                agent=agent_tag,
            )
        else:
            raw = session.llm.call(
                producer=lambda u=call_user: invoker.invoke(u),
                cache_key=cache_key if attempt == 0 else None,
                use_cache=(cache_key is not None) and attempt == 0,
                agent=agent_tag,
            )
        raw_last = raw or ''
        parsed, errors, repaired = parse_and_validate(raw_last, schema)
        if not errors:
            if repaired:
                session.telemetry.emit('schema_repaired', agent=agent_tag)
            return parsed
        if attempt >= max_repair:
            break
        current_user = _repair_user(user_text, raw_last, errors)

    raw_path = _dump_raw(session, agent, raw_last)
    session.telemetry.emit(
        'schema_repair_failed',
        agent=agent,
        errors=errors[:10],
        raw_preview=raw_last[:500],
        raw_path=raw_path,
        partial_keys=sorted(parsed.keys()) if parsed else [],
    )
    return parsed


__all__ = ['invoke_structured', 'parse_and_validate']
