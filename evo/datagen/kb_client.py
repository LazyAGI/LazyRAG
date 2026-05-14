from __future__ import annotations
import logging
import requests

_log = logging.getLogger('evo.datagen.kb_client')


class KBClient:
    def __init__(self, kb_base_url: str, chunk_base_url: str, *, timeout: int = 60) -> None:
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
        for base in _base_candidates(self.kb_base_url):
            for id_key in ('kb_id', 'dataset_id'):
                try:
                    items = self._list_docs(base, id_key, kb_id, algo_id)
                    if items:
                        self.kb_base_url = base
                        self._doc_cache[key] = items
                        return items
                except Exception as exc:
                    _log.warning('get_doc_list base=%s id_key=%s failed: %s', base, id_key, exc)
        self._doc_cache[key] = []
        return []

    def _list_docs(self, base: str, id_key: str, kb_id: str, algo_id: str) -> list[dict]:
        items: list[dict] = []
        page_size = 100
        for page in range(1, 101):
            params = {id_key: kb_id, 'page': page, 'page_size': page_size}
            if id_key == 'kb_id':
                params['algo_id'] = algo_id
            r = self._http.get(f'{base}/v1/docs', params=params, timeout=self.timeout)
            r.raise_for_status()
            batch = r.json().get('data', {}).get('items', [])
            for item in batch:
                doc = item.get('doc') or {}
                rel = item.get('relation') or {}
                snap = item.get('snapshot') or {}
                chunk_kb = snap.get('kb_id') or rel.get('kb_id')
                if chunk_kb:
                    doc['_chunk_kb_id'] = chunk_kb
                items.append(item)
            if len(batch) < page_size:
                break
        return items

    def get_chunks(self, kb_id: str, doc_id: str, algo_id: str = 'general_algo') -> list[dict]:
        return self._get_chunks(kb_id, doc_id, algo_id, rich=False)

    def get_all_chunks(self, kb_id: str, doc_id: str, algo_id: str = 'general_algo') -> list[dict]:
        return self._get_chunks(kb_id, doc_id, algo_id, rich=True)

    def _get_chunks(self, kb_id: str, doc_id: str, algo_id: str, *, rich: bool) -> list[dict]:
        chunk_kb_id = self._chunk_kb_id(kb_id, algo_id, doc_id)
        for group in ('block', 'line'):
            chunks = self._get_chunks_by_group(chunk_kb_id, doc_id, algo_id, group, rich=rich)
            if chunks:
                return chunks
        return []

    def _chunk_kb_id(self, kb_id: str, algo_id: str, doc_id: str) -> str:
        doc = self._find_doc(kb_id, algo_id, doc_id)
        return str(doc.get('_chunk_kb_id') or kb_id)

    def _get_chunks_by_group(self, kb_id: str, doc_id: str, algo_id: str, group: str, *, rich: bool) -> list[dict]:
        for base in _base_candidates(self.chunk_base_url):
            try:
                chunks = []
                page_size = 100
                for page in range(1, 101):
                    r = self._http.get(
                        f'{base}/v1/chunks',
                        params={
                            'kb_id': kb_id,
                            'doc_id': doc_id,
                            'group': group,
                            'algo_id': algo_id,
                            'page': page,
                            'page_size': page_size,
                        },
                        timeout=self.timeout,
                    )
                    r.raise_for_status()
                    items = r.json().get('data', {}).get('items', [])
                    for c in items:
                        content = c.get('content', '').strip()
                        if not content:
                            continue
                        if rich:
                            chunks.append(
                                {
                                    'content': content,
                                    'chunk_id': c.get('uid', ''),
                                    'filename': c.get('metadata', {}).get('file_name', 'unknown'),
                                    'uid': c.get('uid', ''),
                                    'doc_id': c.get('doc_id', doc_id),
                                }
                            )
                        else:
                            chunks.append({'content': content, 'chunk_id': c.get('uid', '')})
                    if len(items) < page_size:
                        break
                if chunks:
                    self.chunk_base_url = base
                    return chunks
            except Exception as exc:
                _log.warning('get_chunks base=%s group=%s failed: %s', base, group, exc)
        return []

    def _find_doc(self, kb_id: str, algo_id: str, doc_id: str) -> dict:
        for item in self.get_doc_list(kb_id, algo_id):
            doc = item.get('doc') or {}
            if doc.get('doc_id') == doc_id:
                return doc
        return {'doc_id': doc_id}

    @classmethod
    def from_config(cls, config) -> 'KBClient':
        return cls(kb_base_url=config.dataset_gen.kb_base_url, chunk_base_url=config.dataset_gen.chunk_base_url)


def _base_candidates(base: str) -> list[str]:
    out = [base.rstrip('/')]
    if '127.0.0.1' in base or 'localhost' in base:
        out.extend(['http://127.0.0.1:18055', 'http://127.0.0.1:28055'])
    return list(dict.fromkeys(out))
