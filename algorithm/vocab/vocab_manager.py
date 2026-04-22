"""VocabManager: 词表管理器，封装 QueryEnhACProcessor，支持热更新。

词表文件格式（JSON 数组）：
    [
        {"cluster_id": "cx", "word": "民法"},
        {"cluster_id": "cx", "word": "民事法律"}
    ]

环境变量：
    LAZYRAG_VOCAB_FILE_PATH  词表 JSON 文件路径（默认 /var/lib/lazyrag/uploads/vocab.json）
"""
from __future__ import annotations

import json
import os
import threading
from typing import Optional, Union

from lazyllm import LOG
from lazyllm.tools.rag.query_enh_ac import QueryEnhACProcessor

_VOCAB_FILE_ENV = 'LAZYRAG_VOCAB_FILE_PATH'
_DEFAULT_VOCAB_FILE = '/var/lib/lazyrag/uploads/vocab.json'


class VocabManager:
    """线程安全的词表管理器，持有 QueryEnhACProcessor 单例并支持热更新。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._file_path: str = os.getenv(_VOCAB_FILE_ENV, _DEFAULT_VOCAB_FILE)
        self._proc = QueryEnhACProcessor(
            data_source=self._load_vocab_file,
            discriminator=None,
        )
        LOG.info(f'[VocabManager] initialized, vocab_file={self._file_path}')

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_vocab_file(self) -> list:
        """从 self._file_path 加载词表，返回记录列表；文件不存在时返回空列表。"""
        path = self._file_path
        try:
            with open(path, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
            if not isinstance(data, list):
                LOG.warning(f'[VocabManager] vocab file root must be a JSON array, got {type(data)}; ignoring.')
                return []
            LOG.info(f'[VocabManager] loaded {len(data)} vocab entries from {path}')
            return data
        except FileNotFoundError:
            LOG.warning(f'[VocabManager] vocab file not found: {path}; using empty vocab.')
            return []
        except Exception as exc:
            LOG.error(f'[VocabManager] failed to load vocab file {path}: {exc}')
            return []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reload(self, file_path: Optional[str] = None) -> int:
        """热更新词表。

        Args:
            file_path: 可选，指定新的词表文件路径；不传则沿用上次路径。

        Returns:
            更新后词表中 word 的总数。
        """
        with self._lock:
            if file_path:
                self._file_path = file_path
                LOG.info(f'[VocabManager] vocab file path updated to {self._file_path}')
            self._proc.update_data_source(self._load_vocab_file)
            count = len(self._proc.word_to_cluster)
            LOG.info(f'[VocabManager] reloaded, vocab_size={count}')
            return count

    def __call__(self, query: Union[str, list]) -> Union[str, list]:
        """对 query 进行词表增强后返回；未命中或 discriminator 为 None 时原样返回。"""
        with self._lock:
            return self._proc(query)

    @property
    def vocab_size(self) -> int:
        """当前加载的 word 数量。"""
        with self._lock:
            return len(self._proc.word_to_cluster)

    @property
    def file_path(self) -> str:
        return self._file_path


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_manager: Optional[VocabManager] = None
_init_lock = threading.Lock()


def get_vocab_manager() -> VocabManager:
    """返回全局 VocabManager 单例（惰性初始化）。"""
    global _manager
    if _manager is None:
        with _init_lock:
            if _manager is None:
                _manager = VocabManager()
    return _manager
