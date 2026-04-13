from datetime import date
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict
from lazyllm import LOG
from lazyllm.module import ModuleBase
from lazyllm.components import ChatPrompter
from lazyllm.components.formatter import JsonFormatter

from chat.utils.schema import BaseMessage, SessionMemory
from chat.prompts.rewrite import MULTITURN_QUERY_REWRITE_PROMPT


class RewriterInput(BaseModel):
    """
    多轮对话 Query 改写器 的输入结构
    —— 对应此前的“调用输入模板（User Prompt / 模型输入）”
    """
    model_config = ConfigDict(
        extra='forbid',
        json_schema_extra={
            'example': {
                'chat_history': [
                    {
                        'role': 'user',
                        'content': '对比下 Qwen 与 Llama 的推理性能',
                        'time': '2025-08-11T10:00:00+09:00',
                    },
                    {'role': 'assistant', 'content': '已对比：A100 上 Qwen-32B > Llama-34B ...'},
                ],
                'last_user_query': '那它在多图输入时差异大吗？近两个月的数据就行',
                'has_appendix': False,
                'current_date': '2025-08-12',
                'user_locale': 'zh',
                'session_memory': {
                    'topic': '多模型推理对比',
                    'entities': ['Qwen-32B', 'Llama-34B'],
                    'time_hints': ['近两个月'],
                    'source_scope': ['官方博客', '评测报告'],
                },
            }
        })

    chat_history: List[BaseMessage] = Field(..., description='过去 N 轮对话')
    last_user_query: str = Field(..., description='用户最新一句')
    current_date: date = Field(..., description='用于相对时间归一的当前日期（YYYY-MM-DD）')
    user_locale: Optional[str] = Field(default='zh', description='用户首选语言（如 zh/en），可选')
    has_appendix: bool = Field(False, description='是否包含附件')
    session_memory: Optional[SessionMemory] = Field(
        default=None,
        description='会话内已确定的实体/意图/约束（可选）',
    )


class MultiturnQueryRewriter(ModuleBase):

    def __init__(
        self,
        llm,
        return_trace: bool = False,
    ) -> None:
        super().__init__(return_trace=return_trace)
        self._llm = llm.share(prompt=ChatPrompter(instruction=MULTITURN_QUERY_REWRITE_PROMPT), format=JsonFormatter())

    def forward(self, input: dict, session_id: str = None, **kwargs):
        user_input = input
        query = user_input.get('query', '')
        llm_chat_history = user_input.get('history', [])
        has_appendix = kwargs.pop('has_appendix', False)
        records = [BaseMessage(**history) for history in llm_chat_history]
        rewrite_input = RewriterInput(chat_history=records, last_user_query=query, current_date=date.today(),
                                      has_appendix=has_appendix)

        res = self._llm(rewrite_input.model_dump_json(), **kwargs)
        LOG.info(f'[MultiturnQueryRewriter] [res={res}]')
        if isinstance(res, dict):
            user_input['query'] = res.get('rewritten_query')
            user_input['origin_query'] = query
        return user_input
