from __future__ import annotations

import httpx


class HttpEvalProvider:
    def __init__(self, base_url: str, *,
                 token: str = '',
                 timeout_s: float = 600.0) -> None:
        self._base = base_url.rstrip('/')
        headers = {'Accept': 'application/json'}
        if token:
            headers['Authorization'] = f'Bearer {token}'
        self._client = httpx.Client(headers=headers, timeout=timeout_s)

    def get_eval_report(self, eval_id: str) -> dict:
        r = self._client.get(f'{self._base}/evals/{eval_id}')
        r.raise_for_status()
        return r.json()

    def list_evals(self, *, kb_id: str | None = None) -> list[dict]:
        params = {'kb_id': kb_id} if kb_id else None
        r = self._client.get(f'{self._base}/evals', params=params)
        r.raise_for_status()
        return r.json()

    def run_eval(self, *, dataset_id: str, target_chat_url: str,
                 options: dict | None = None) -> dict:
        r = self._client.post(f'{self._base}/evals',
                                json={'dataset_id': dataset_id,
                                      'target_chat_url': target_chat_url,
                                      'options': options or {}})
        r.raise_for_status()
        return r.json()
