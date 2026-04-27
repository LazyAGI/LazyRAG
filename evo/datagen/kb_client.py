from __future__ import annotations

import logging
from typing import Any

import requests

_log = logging.getLogger('evo.datagen.kb_client')


class KBClient:
    def __init__(self, kb_base_url: str, chunk_base_url: str, *, timeout: int = 20) -> None:
        self.kb_base_url = kb_base_url.rstrip('/')
        self.chunk_base_url = chunk_base_url.rstrip('/')
        self.timeout = timeout
        self._doc_cache: dict[tuple[str, str], list[dict]] = {}
        self._http = requests.Session()
        self._http.trust_env = False

    def get_doc_list(self, kb_id: str, algo_id: str = 'general_algo') -> list[dict]:
        key = (kb_id, algo_id)
        if key in self._doc_cache:
            return self._doc_cache[key]
        try:
            r = self._http.get(
                f'{self.kb_base_url}/v1/docs',
                params={'kb_id': kb_id, 'algo_id': algo_id, 'page': 1, 'page_size': 20},
                timeout=self.timeout,
            )
            r.raise_for_status()
            items = r.json().get('data', {}).get('items', [])
            self._doc_cache[key] = items
            return items
        except Exception as exc:
            _log.warning('get_doc_list failed: %s', exc)
            return []

    def get_chunks(self, kb_id: str, doc_id: str, algo_id: str = 'general_algo') -> list[dict]:
        return self._get_chunks(kb_id, doc_id, algo_id, rich=False)

    def get_all_chunks(self, kb_id: str, doc_id: str, algo_id: str = 'general_algo') -> list[dict]:
        return self._get_chunks(kb_id, doc_id, algo_id, rich=True)

    def _get_chunks(self, kb_id: str, doc_id: str, algo_id: str, *, rich: bool) -> list[dict]:
        for group in ('block', 'line'):
            chunks = self._get_chunks_by_group(kb_id, doc_id, algo_id, group, rich=rich)
            if chunks:
                return chunks
        return []

    def _get_chunks_by_group(
        self, kb_id: str, doc_id: str, algo_id: str, group: str, *, rich: bool,
    ) -> list[dict]:
        try:
            r = self._http.get(
                f'{self.chunk_base_url}/v1/chunks',
                params={'kb_id': kb_id, 'doc_id': doc_id,
                        'group': group, 'algo_id': algo_id, 'page': 1, 'page_size': 10},
                timeout=self.timeout,
            )
            r.raise_for_status()
            items = r.json().get('data', {}).get('items', [])
            chunks = []
            for c in items:
                content = c.get('content', '').strip()
                if not content:
                    continue
                if rich:
                    chunks.append({
                    'content': c.get('content', '').strip(),
                    'chunk_id': c.get('uid', ''),
                    'filename': c.get('metadata', {}).get('file_name', 'unknown'),
                    'uid': c.get('uid', ''),
                    'doc_id': c.get('doc_id', doc_id),
                    })
                else:
                    chunks.append({'content': content, 'chunk_id': c.get('uid', '')})
            return chunks
        except Exception as exc:
            _log.warning('get_chunks group=%s failed: %s', group, exc)
            return []

    @classmethod
    def from_config(cls, config) -> 'KBClient':
        return cls(
            kb_base_url=config.dataset_gen.kb_base_url,
            chunk_base_url=config.dataset_gen.chunk_base_url,
        )
