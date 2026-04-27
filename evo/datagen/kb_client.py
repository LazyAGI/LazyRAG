from __future__ import annotations

import logging
from typing import Any

import requests

_log = logging.getLogger('evo.datagen.kb_client')


class KBClient:
    def __init__(self, kb_base_url: str, chunk_base_url: str, *, timeout: int = 10) -> None:
        self.kb_base_url = kb_base_url.rstrip('/')
        self.chunk_base_url = chunk_base_url.rstrip('/')
        self.timeout = timeout

    def get_doc_list(self, kb_id: str, algo_id: str = 'general_algo') -> list[dict]:
        try:
            r = requests.get(
                f'{self.kb_base_url}/v1/docs',
                params={'kb_id': kb_id, 'algo_id': algo_id},
                timeout=self.timeout,
            )
            r.raise_for_status()
            return r.json().get('data', {}).get('items', [])
        except Exception as exc:
            _log.warning('get_doc_list failed: %s', exc)
            return []

    def get_chunks(self, kb_id: str, doc_id: str, algo_id: str = 'general_algo') -> list[dict]:
        try:
            r = requests.get(
                f'{self.chunk_base_url}/v1/chunks',
                params={'kb_id': kb_id, 'doc_id': doc_id,
                        'group': 'block', 'algo_id': algo_id},
                timeout=self.timeout,
            )
            r.raise_for_status()
            items = r.json().get('data', {}).get('items', [])
            return [
                {'content': c['content'].strip(), 'chunk_id': c.get('uid', '')}
                for c in items if c.get('content', '').strip()
            ]
        except Exception as exc:
            _log.warning('get_chunks failed: %s', exc)
            return []

    def get_all_chunks(self, kb_id: str, doc_id: str, algo_id: str = 'general_algo') -> list[dict]:
        try:
            r = requests.get(
                f'{self.chunk_base_url}/v1/chunks',
                params={'kb_id': kb_id, 'doc_id': doc_id,
                        'group': 'block', 'algo_id': algo_id},
                timeout=self.timeout,
            )
            r.raise_for_status()
            items = r.json().get('data', {}).get('items', [])
            return [
                {
                    'content': c.get('content', '').strip(),
                    'chunk_id': c.get('uid', ''),
                    'filename': c.get('metadata', {}).get('file_name', 'unknown'),
                    'uid': c.get('uid', ''),
                    'doc_id': c.get('doc_id', doc_id),
                }
                for c in items if c.get('content', '').strip()
            ]
        except Exception as exc:
            _log.warning('get_all_chunks failed: %s', exc)
            return []

    @classmethod
    def from_config(cls, config) -> 'KBClient':
        return cls(
            kb_base_url=config.dataset_gen.kb_base_url,
            chunk_base_url=config.dataset_gen.chunk_base_url,
        )
