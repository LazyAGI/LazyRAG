# 检索组件
# 本层内主要存放get_ppl_search流程中用于从数据库中召回的组件
# get_retriever.py - 远程 Document/Retriever 与临时文件检索 pipeline
# get_ppl_search.py - 召回部分的核心流程
# adaptive_topk.py - 自适应topk选择组件

from chat.components.retrieve.get_retriever import (
    SearchRetrievalParts,
    setup_search_retrieval,
    get_remote_docment,
)
from chat.components.retrieve.adaptive_topk import AdaptiveKComponent

__all__ = [
    'SearchRetrievalParts',
    'setup_search_retrieval',
    'AdaptiveKComponent',
    'get_remote_docment',
]
