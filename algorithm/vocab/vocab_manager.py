"""VocabManager: 多用户词表管理器，封装 QueryEnhACProcessor，支持热更新。

每个用户（create_user_id）维护独立的 QueryEnhACProcessor 实例，词表数据从
PostgreSQL lazyrag_vocab 表中按 create_user_id 查询。

用法：
    # 后端通知算法服务热更新某用户词表
    get_vocab_manager('user_001').reload()

    # 检索前对 query 进行词表增强（pipeline 中使用）
    enhanced = get_vocab_manager('user_001')('用户的 query 文本')

环境变量：
    LAZYRAG_DATABASE_URL  PostgreSQL 连接 URL
"""
from __future__ import annotations

import threading
from typing import Callable, List, Optional, Union

from lazyllm import LOG
from lazyllm.tools.rag.query_enh_ac import QueryEnhACProcessor

from .db import fetch_vocab_for_create_user_id


class VocabManager:
    """单用户词表管理器：绑定一个 create_user_id，从 DB 加载词表，支持热更新。

    Args:
        create_user_id: 用户标识（对应 lazyrag_vocab.create_user_id）。
        data_source: 可选，自定义数据源（callable 或 list）；
                     主要用于测试，省略时从数据库加载。
    """

    def __init__(self, create_user_id: str = '', *, data_source: Optional[Callable] = None) -> None:
        self._create_user_id = create_user_id
        self._lock = threading.RLock()
        actual_source = data_source if data_source is not None else self._load_from_db
        self._proc = QueryEnhACProcessor(
            data_source=actual_source,
            discriminator=None,
        )
        LOG.info(f'[VocabManager] initialized for create_user_id={create_user_id!r}, vocab_size={self.vocab_size}')

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_from_db(self) -> List[dict]:
        """从 lazyrag_vocab 加载当前用户的词表行，字段格式与 QueryEnhACProcessor 匹配。"""
        return fetch_vocab_for_create_user_id(self._create_user_id)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reload(self) -> int:
        """热更新：从数据库重新查询词表并重建 AC 自动机。

        Returns:
            更新后词表中 word 的总数。
        """
        with self._lock:
            self._proc.update_data_source(self._load_from_db)
            count = len(self._proc.word_to_cluster)
            LOG.info(f'[VocabManager] reloaded for create_user_id={self._create_user_id!r}, vocab_size={count}')
            return count

    def __call__(self, query: Union[str, list]) -> Union[str, list]:
        """对 query 进行词表增强后返回；词表为空或 discriminator=None 时原样返回。"""
        with self._lock:
            return self._proc(query)

    @property
    def vocab_size(self) -> int:
        """当前加载的 word 数量。"""
        with self._lock:
            return len(self._proc.word_to_cluster)

    @property
    def create_user_id(self) -> str:
        return self._create_user_id


# ---------------------------------------------------------------------------
# Multi-user registry（替换原来的模块级单例）
# ---------------------------------------------------------------------------

_registry: dict = {}
_registry_lock = threading.Lock()


def get_vocab_manager(create_user_id: str = '') -> VocabManager:
    """返回 create_user_id 对应的 VocabManager（惰性初始化，每个 create_user_id 一个实例）。

    Args:
        create_user_id: 用户标识，对应 lazyrag_vocab.create_user_id。
                 传空字符串时返回"无用户"的默认管理器（词表通常为空）。
    """
    if create_user_id not in _registry:
        with _registry_lock:
            if create_user_id not in _registry:
                _registry[create_user_id] = VocabManager(create_user_id)
    return _registry[create_user_id]


def clear_registry() -> None:
    """清空注册表（仅用于测试，确保用例间互相隔离）。"""
    with _registry_lock:
        _registry.clear()
