from __future__ import annotations

import json
import logging
from typing import Any

_log = logging.getLogger('evo.datagen.llm')


def chat(prompt: str, *, llm_factory=None) -> Any:
    if llm_factory is None:
        raise RuntimeError('llm_factory required for datagen.chat')
    raw = llm_factory()(prompt)
    if isinstance(raw, list):
        raw = raw[-1]
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception as exc:
            _log.warning('json parse failed: %s', exc)
            return raw
    return raw
