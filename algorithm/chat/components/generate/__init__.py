# 生成组件
# 本层主要存放生成相关的组件
# get_ppl_generate.py - LLM生成pipeline
# aggregate.py - 结果聚合组件
# prompt_formatter.py - 提示词格式化组件
# output_parser.py - 输出解析组件

from chat.components.generate.aggregate import AggregateComponent
from chat.components.generate.prompt_formatter import RAGContextFormatter
from chat.components.generate.output_parser import CustomOutputParser

__all__ = [
    'AggregateComponent',
    'RAGContextFormatter',
    'CustomOutputParser',
]
