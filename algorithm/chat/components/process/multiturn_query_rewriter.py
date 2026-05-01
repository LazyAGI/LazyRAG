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
    """Input schema for the multi-turn query rewriter."""
    model_config = ConfigDict(
        extra='forbid',
        json_schema_extra={
            'example': {
                'chat_history': [
                    {
                        'role': 'user',
                        'content': 'Compare the inference performance of Qwen and Llama',
                        'time': '2025-08-11T10:00:00+09:00',
                    },
                    {'role': 'assistant', 'content': 'Compared: on A100, Qwen-32B > Llama-34B ...'},
                ],
                'last_user_query': 'Is the difference large for multi-image input? Data from the past two months is fine.',  # noqa: E501
                'has_appendix': False,
                'current_date': '2025-08-12',
                'user_locale': 'zh',
                'session_memory': {
                    'topic': 'Multi-model inference comparison',
                    'entities': ['Qwen-32B', 'Llama-34B'],
                    'time_hints': ['past two months'],
                    'source_scope': ['official blog', 'benchmark reports'],
                },
            }
        })

    chat_history: List[BaseMessage] = Field(..., description='Past N turns of conversation')
    last_user_query: str = Field(..., description="The user's latest message")
    current_date: date = Field(..., description='Current date for relative time normalization (YYYY-MM-DD)')
    user_locale: Optional[str] = Field(default='zh', description='User preferred language (e.g. zh/en), optional')
    has_appendix: bool = Field(False, description='Whether an attachment is included')
    session_memory: Optional[SessionMemory] = Field(
        default=None,
        description='Confirmed entities/intents/constraints within the session (optional)',
    )


class MultiturnQueryRewriter(ModuleBase):

    def __init__(
        self,
        llm,
        return_trace: bool = False,
    ) -> None:
        super().__init__(return_trace=return_trace)
        self._llm = llm.share(
            prompt=ChatPrompter(instruction=MULTITURN_QUERY_REWRITE_PROMPT),
            format=JsonFormatter(),
            stream=False,
        )

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
