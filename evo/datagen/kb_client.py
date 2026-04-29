from __future__ import annotations

import json
import logging
import re
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import requests

_log = logging.getLogger('evo.datagen.kb_client')


class KBClient:
    def __init__(self, kb_base_url: str, chunk_base_url: str, *, timeout: int = 60) -> None:
        self.kb_base_url = kb_base_url.rstrip('/')
        self.chunk_base_url = chunk_base_url.rstrip('/')
        self.timeout = timeout
        self._doc_cache: dict[tuple[str, str], list[dict]] = {}
        self._file_chunk_cache: dict[tuple[str, str], list[dict]] = {}
        self._http = requests.Session()
        self._http.trust_env = False

    def get_doc_list(self, kb_id: str, algo_id: str = 'general_algo') -> list[dict]:
        key = (kb_id, algo_id)
        if key in self._doc_cache:
            return self._doc_cache[key]
        try:
            items: list[dict] = []
            page_size = 100
            for page in range(1, 101):
                r = self._http.get(
                    f'{self.kb_base_url}/v1/docs',
                    params={'kb_id': kb_id, 'algo_id': algo_id,
                            'page': page, 'page_size': page_size},
                    timeout=self.timeout,
                )
                r.raise_for_status()
                batch = r.json().get('data', {}).get('items', [])
                items.extend(batch)
                if len(batch) < page_size:
                    break
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
        return self._get_chunks_from_doc_file(kb_id, doc_id, algo_id, rich=rich)

    def _get_chunks_by_group(
        self, kb_id: str, doc_id: str, algo_id: str, group: str, *, rich: bool,
    ) -> list[dict]:
        try:
            chunks = []
            page_size = 100
            for page in range(1, 101):
                r = self._http.get(
                    f'{self.chunk_base_url}/v1/chunks',
                    params={'kb_id': kb_id, 'doc_id': doc_id,
                            'group': group, 'algo_id': algo_id,
                            'page': page, 'page_size': page_size},
                    timeout=self.timeout,
                )
                r.raise_for_status()
                items = r.json().get('data', {}).get('items', [])
                for c in items:
                    content = c.get('content', '').strip()
                    if not content:
                        continue
                    if rich:
                        chunks.append({
                            'content': content,
                            'chunk_id': c.get('uid', ''),
                            'filename': c.get('metadata', {}).get('file_name', 'unknown'),
                            'uid': c.get('uid', ''),
                            'doc_id': c.get('doc_id', doc_id),
                        })
                    else:
                        chunks.append({'content': content, 'chunk_id': c.get('uid', '')})
                if len(items) < page_size:
                    break
            return chunks
        except Exception as exc:
            _log.warning('get_chunks group=%s failed: %s', group, exc)
            return []

    def _get_chunks_from_doc_file(
        self, kb_id: str, doc_id: str, algo_id: str, *, rich: bool,
    ) -> list[dict]:
        key = (kb_id, doc_id)
        if key not in self._file_chunk_cache:
            doc = self._find_doc(kb_id, algo_id, doc_id)
            path = _doc_path(doc)
            text = _extract_text(path) if path else ''
            self._file_chunk_cache[key] = _split_text(text, doc_id, doc)
            if not self._file_chunk_cache[key]:
                _log.warning('no chunks from API or file for doc_id=%s path=%s', doc_id, path)
        chunks = self._file_chunk_cache[key]
        if rich:
            return chunks
        return [{'content': c['content'], 'chunk_id': c['chunk_id']} for c in chunks]

    def _find_doc(self, kb_id: str, algo_id: str, doc_id: str) -> dict:
        for item in self.get_doc_list(kb_id, algo_id):
            doc = item.get('doc') or {}
            if doc.get('doc_id') == doc_id:
                return doc
        return {'doc_id': doc_id}

    @classmethod
    def from_config(cls, config) -> 'KBClient':
        return cls(
            kb_base_url=config.dataset_gen.kb_base_url,
            chunk_base_url=config.dataset_gen.chunk_base_url,
        )


def _doc_path(doc: dict) -> Path | None:
    for key in ('path', 'file_path'):
        if doc.get(key):
            return Path(str(doc[key]))
    meta = doc.get('metadata') or {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except Exception:
            meta = {}
    for key in ('core_parse_stored_path', 'core_stored_path', 'external_file_path'):
        if isinstance(meta, dict) and meta.get(key):
            return Path(str(meta[key]))
    return None


def _extract_text(path: Path | None) -> str:
    if not path or not path.exists():
        return ''
    suffix = path.suffix.lower()
    if suffix == '.pdf':
        return _extract_pdf(path)
    if suffix == '.docx':
        return _extract_docx(path)
    try:
        return path.read_text(encoding='utf-8', errors='ignore')
    except Exception as exc:
        _log.warning('read doc file failed path=%s: %s', path, exc)
        return ''


def _extract_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        parts = []
        for page in reader.pages[:40]:
            parts.append(page.extract_text() or '')
        return '\n'.join(parts)
    except Exception as exc:
        _log.warning('extract pdf failed path=%s: %s', path, exc)
        return ''


def _extract_docx(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as zf:
            xml = zf.read('word/document.xml')
        root = ElementTree.fromstring(xml)
        return '\n'.join(node.text or '' for node in root.iter()
                         if node.tag.endswith('}t') and node.text)
    except Exception as exc:
        _log.warning('extract docx failed path=%s: %s', path, exc)
        return ''


def _split_text(text: str, doc_id: str, doc: dict) -> list[dict]:
    clean = re.sub(r'\n{3,}', '\n\n', text).strip()
    if not clean:
        return []
    filename = doc.get('filename') or doc.get('name') or doc_id
    chunks = []
    size, overlap = 1200, 160
    pos = 0
    while pos < len(clean) and len(chunks) < 80:
        part = clean[pos:pos + size].strip()
        if len(part) >= 80:
            idx = len(chunks)
            chunk_id = f'file:{doc_id}:{idx}'
            chunks.append({
                'content': part,
                'chunk_id': chunk_id,
                'uid': chunk_id,
                'filename': filename,
                'doc_id': doc_id,
            })
        pos += size - overlap
    return chunks
