from __future__ import annotations
import json
import logging
import re
from typing import Any
import json_repair
_log = logging.getLogger('evo.datagen.llm')
def chat(prompt: str, *, llm_factory=None) -> Any:
    if llm_factory is None:
        raise RuntimeError('llm_factory required for datagen.chat')
    raw = llm_factory()(prompt)
    if isinstance(raw, list):
        raw = raw[-1]
    if isinstance(raw, str):
        return _parse_jsonish(raw)
    return raw
def _parse_jsonish(raw: str) -> Any:
    text = re.sub('<think>.*?</think>', '', raw, flags=re.DOTALL).strip()
    text = text.replace('```json', '').replace('```', '').strip()
    for candidate in (text, _extract_json_object(text)):
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except Exception:
            try:
                return json_repair.loads(candidate)
            except Exception as exc:
                _log.debug('json parse candidate failed: %s', exc)
    _log.warning('json parse failed; returning raw text')
    return text
def _extract_json_object(text: str) -> str:
    start = text.find('{')
    end = text.rfind('}')
    if start >= 0 and end > start:
        return text[start:end + 1]
    return ''
