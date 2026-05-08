from __future__ import annotations

import os
from typing import Any, Dict, List
from urllib.parse import urlparse

from lazyllm import LOG, ModuleBase
from lazyllm.components.formatter import encode_query_with_filepaths


_IMAGE_DESCRIBE_PROMPT = (
    'Briefly describe what the image contains, then return a single concise sentence in plain text.'
)

_REMOTE_SCHEMES = ('http', 'https', 'file')


class QueryImageRewriter(ModuleBase):
    '''Augment the user query with VLM-derived descriptions of attached images.

    Inaccessible local paths are silently skipped (with a warning); remote URLs
    are passed through untouched.  When all paths are filtered out, the query
    is returned unchanged so the downstream pipeline behaves as if no images
    were attached.
    '''

    def __init__(self, llm: Any, return_trace: bool = False, **kwargs):
        super().__init__(return_trace=return_trace, **kwargs)
        self.llm = llm

    def _extract_paths(self, payload: Dict[str, Any]) -> List[str]:
        paths = payload.get('query_images') or []
        if not isinstance(paths, list):
            return []
        return [str(path).strip() for path in paths if str(path).strip()]

    @staticmethod
    def _is_remote(path: str) -> bool:
        try:
            parsed = urlparse(path)
        except Exception:
            return False
        return parsed.scheme in _REMOTE_SCHEMES

    def _filter_accessible_paths(self, paths: List[str]) -> List[str]:
        valid: List[str] = []
        for p in paths:
            if self._is_remote(p):
                valid.append(p)
                continue
            if os.path.isfile(p) and os.access(p, os.R_OK):
                valid.append(p)
            else:
                LOG.warning(f'[QueryImageRewriter] skip inaccessible image path: {p}')
        return valid

    def _extract_text(self, llm_output: Any) -> str:
        if isinstance(llm_output, str):
            return llm_output.strip()
        if isinstance(llm_output, dict):
            for key in ('text', 'content', 'answer'):
                value = llm_output.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return str(llm_output).strip()

    def forward(self, input: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        payload = dict(input or {})
        query = str(payload.get('query', '')).strip()
        image_paths = self._filter_accessible_paths(self._extract_paths(payload))
        if not query or not image_paths:
            return payload

        encoded_query = encode_query_with_filepaths(_IMAGE_DESCRIBE_PROMPT, image_paths)
        priority = payload.get('priority', 0)
        llm_output = self.llm(
            encoded_query,
            stream_output=False,
            llm_chat_history=[],
            lazyllm_files=None,
            priority=priority,
        )
        image_desc = self._extract_text(llm_output)
        if image_desc:
            payload['query'] = f'{query}\n\nImage context: {image_desc}'
        return payload
