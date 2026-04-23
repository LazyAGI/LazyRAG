from __future__ import annotations

from typing import Any

import httpx


class HttpLLM:
    def __init__(self, base_url: str, role: str, token: str,
                 *, system_prompt: str | None = None, timeout: float = 60.0) -> None:
        self._base = base_url.rstrip('/')
        self._role = role
        self._token = token
        self._sys = system_prompt
        self._timeout = timeout

    def share(self, *, prompt: Any = None, **_: Any) -> 'HttpLLM':
        sys_text = self._sys
        if prompt is not None:
            sys_text = (
                getattr(prompt, 'instruction', None)
                or getattr(prompt, '_instruction', None)
                or str(prompt)
            )
        return HttpLLM(self._base, self._role, self._token,
                       system_prompt=sys_text, timeout=self._timeout)

    def __call__(self, user_text: str, **_: Any) -> str:
        with httpx.Client(timeout=self._timeout) as c:
            r = c.post(
                f'{self._base}/internal/llm/call',
                headers={'X-Internal-Token': self._token},
                json={'role': self._role, 'system_prompt': self._sys,
                      'user_text': user_text},
            )
            r.raise_for_status()
            return r.json()['output']


class HttpEmbed:
    def __init__(self, base_url: str, role: str, token: str,
                 *, timeout: float = 60.0) -> None:
        self._base = base_url.rstrip('/')
        self._role = role
        self._token = token
        self._timeout = timeout

    def __call__(self, text: str | list[str], **_: Any) -> list[float] | list[list[float]]:
        single = isinstance(text, str)
        texts = [text] if single else list(text)
        with httpx.Client(timeout=self._timeout) as c:
            r = c.post(
                f'{self._base}/internal/embed/call',
                headers={'X-Internal-Token': self._token},
                json={'role': self._role, 'texts': texts},
            )
            r.raise_for_status()
            vectors = r.json()['vectors']
        return vectors[0] if single else vectors
