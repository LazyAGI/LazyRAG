from __future__ import annotations

import json
import logging
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from evo.datagen.kb_client import KBClient
from evo.runtime.fs import atomic_write_json

_log = logging.getLogger('evo.datagen.corpus')


@dataclass
class CorpusIndex:
    kb_id: str
    algo_id: str
    docs: list[dict]
    chunks: list[dict]

    def sample(self, count: int, pred: Callable[[str], bool] | None = None) -> list[dict]:
        rows = [c for c in self.chunks if pred is None or pred(c.get('content', ''))]
        random.shuffle(rows)
        return rows[:count]

    def to_dict(self) -> dict[str, Any]:
        return {
            'kb_id': self.kb_id,
            'algo_id': self.algo_id,
            'docs': self.docs,
            'chunks': self.chunks,
            'created_at': time.time(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'CorpusIndex':
        return cls(
            kb_id=str(data.get('kb_id') or ''),
            algo_id=str(data.get('algo_id') or ''),
            docs=list(data.get('docs') or []),
            chunks=list(data.get('chunks') or []),
        )


def build_corpus_index(
    ds: KBClient,
    kb_id: str,
    algo_id: str,
    *,
    cache_dir: Path | None = None,
    docs: list[dict] | None = None,
    max_docs: int = 48,
    max_chunks: int = 160,
    max_workers: int = 8,
) -> CorpusIndex:
    cache = _cache_path(cache_dir, kb_id, algo_id) if cache_dir else None
    if cache and cache.is_file():
        try:
            data = json.loads(cache.read_text(encoding='utf-8'))
            idx = CorpusIndex.from_dict(data)
            if idx.chunks:
                _log.info('loaded corpus index cache chunks=%s docs=%s',
                          len(idx.chunks), len(idx.docs))
                return idx
        except Exception as exc:
            _log.warning('ignore invalid corpus cache %s: %s', cache, exc)

    docs = docs if docs is not None else ds.get_doc_list(kb_id, algo_id)
    selected = list(docs)
    random.shuffle(selected)
    selected = selected[:max_docs]
    chunks: list[dict] = []
    workers = max(1, min(max_workers, len(selected) or 1))
    pool = ThreadPoolExecutor(max_workers=workers)
    try:
        futures = {pool.submit(_doc_chunks, ds, kb_id, algo_id, item): item
                   for item in selected}
        for future in as_completed(futures):
            chunks.extend(future.result())
            if len(chunks) >= max_chunks:
                for pending in futures:
                    if pending is not future:
                        pending.cancel()
                pool.shutdown(wait=False, cancel_futures=True)
                break
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    random.shuffle(chunks)
    idx = CorpusIndex(kb_id=kb_id, algo_id=algo_id, docs=docs,
                      chunks=chunks[:max_chunks])
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(cache, idx.to_dict())
    _log.info('built corpus index chunks=%s docs=%s/%s',
              len(idx.chunks), len(selected), len(docs))
    return idx


def _doc_chunks(ds: KBClient, kb_id: str, algo_id: str, item: dict) -> list[dict]:
    doc = item.get('doc') or {}
    doc_id = doc.get('doc_id', '')
    if not doc_id:
        return []
    filename = doc.get('filename') or doc.get('name') or doc_id
    rows = []
    for chunk in ds.get_all_chunks(kb_id, doc_id, algo_id):
        content = str(chunk.get('content') or '').strip()
        if len(content) < 80:
            continue
        rows.append({
            'content': content,
            'chunk_id': chunk.get('chunk_id') or chunk.get('uid', ''),
            'uid': chunk.get('uid') or chunk.get('chunk_id') or '',
            'doc_id': chunk.get('doc_id') or doc_id,
            'filename': chunk.get('filename') or filename,
        })
    return rows


def _cache_path(cache_dir: Path | None, kb_id: str, algo_id: str) -> Path | None:
    if cache_dir is None:
        return None
    safe = ''.join(ch if ch.isalnum() or ch in '._-' else '_' for ch in f'{kb_id}_{algo_id}')
    return cache_dir / f'{safe}.json'
