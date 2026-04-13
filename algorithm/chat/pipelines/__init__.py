# 核心流水线定义
# 包含了agentic和naive两种模式，分别对应agentic.py和naive.py

from chat.pipelines.agentic import get_ppl_agentic, agentic_rag
from chat.pipelines.naive import get_ppl_naive

__all__ = [
    'get_ppl_agentic',
    'get_ppl_naive',
    'agentic_rag',
]
