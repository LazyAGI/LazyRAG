from datetime import date
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict
from lazyllm import LOG
from lazyllm.module import ModuleBase
from lazyllm.components import ChatPrompter
from lazyllm.components.formatter import JsonFormatter

from chat.utils.message import BaseMessage, SessionMemory


MULTITURN_QUERY_REWRITE_PROMPT = """
你是“多轮对话 Query 改写器”。在检索前，将用户最后一问改写成
【语义完整、上下文自洽、可独立理解】的一句话查询。只做改写，不回答。

必须遵守：
1) 遵循**保守改写**原则
    - 仅在必要时改写：指代不明、关键约束仅存在于上下文、多轮任务延续等
    - 若 last_user_query 脱离任何上下文仍语义完整，不得进行任何程度的加工和改写（名词替换、句式调整等）。
2) 结合 chat_history 与 session_memory 解析指代与省略；继承已给出的时间/地点/来源/语言等约束。
    - 输入中提供变量 has_appendix 表示用户是否上传了附件。若 last_user_query 中存在指示代词
      （如“这是谁 / 这两个人 / 这里 / 那张表”），必须先判断指代来源是历史对话还是上传的附件；确保不把附件指代误改写为历史内容，或反之。
    - 若指代来源无法确定，则保持保守改写或不改写，不做臆测。
3) 将“今天/近两年/上周”等相对时间，基于 current_date 归一为绝对日期或区间。
4) 不臆造事实或新增约束；若存在歧义，做**保守改写**并下调 confidence，在 rationale_short 说明原因。
5) 若上轮限定了信息源/文档集合，需在 rewritten_query 和 constraints.filters.source 中显式保留。
6) 语言跟随 last_user_query；若提供 user_locale 且一致，则优先使用该语言。
7) 仅输出一个 JSON 对象；不要包含除规定字段外的任何内容。

输出 JSON（严格按此结构）：
{
  "rewritten_query": "<面向检索的一句话，完整可独立理解>",
  "language": "zh",
  "constraints": {
    "must_include": [],
    "filters": {
      "time": { "from": null, "to": null, "points": [] },
      "source": [],
      "entity": []
    },
    "exclude_terms": []
  },
  "confidence": 0.0,
  "rationale_short": "<1-2句说明改写要点/歧义与处理>"
}
"""


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
