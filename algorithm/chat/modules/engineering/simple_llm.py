import asyncio
from typing import Optional, Any, List
from pydantic import BaseModel, Field

import lazyllm
from lazyllm import ModuleBase
from lazyllm.module import OnlineChatModuleBase
from lazyllm.components.prompter import PrompterBase
from lazyllm.components.formatter import FormatterBase


class LlmStrategy(BaseModel):
    temperature: Optional[float] = Field(
        0.01, ge=0.0, le=1.0, description='采样温度，取值范围为[0.0, 1.0]，默认值为0.01'
    )
    max_tokens: Optional[int] = Field(
        4096, ge=1, le=16048, description='最大token数，取值范围为[1, 16048]，默认值为4096'
    )
    frequency_penalty: Optional[float] = Field(
        0,
        ge=-2.0,
        le=2.0,
        description='重复惩罚，取值范围为[-2.0, 2.0]，默认值为0。正值为减少产生相同token的频率。',
    )
    priority: Optional[int] = Field(
        0,
        description=(
            '请求优先级，用于vllm调度。数值越大优先级越高，默认值为None（使用系统默认优先级）'
        ),
    )

    class Config:
        extra = 'allow'


class SimpleLlmComponent(ModuleBase):
    def __init__(
        self,
        llm: OnlineChatModuleBase,
        prompter=None,
        return_trace: bool = False,
        **kwargs,
    ):
        super().__init__(return_trace=return_trace)
        self.llm = llm

    @property
    def series(self):
        return 'LlmComponent'

    @property
    def type(self):
        return 'LLM'

    def share(
        self,
        prompt: PrompterBase = None,
        format: FormatterBase = None,
        stream: Optional[bool] = None,
        history: List[List[str]] = None,
        copy_static_params: bool = False,
    ):
        self.llm = self.llm.share(
            prompt=prompt,
            format=format,
            stream=stream,
            history=history,
            copy_static_params=copy_static_params,
        )
        return self

    async def astream_iterator(self, input, llm, files, llm_chat_history=None, **kwargs):
        if llm_chat_history is None:
            llm_chat_history = []
        with lazyllm.ThreadPoolExecutor(1) as executor:
            future = executor.submit(
                llm,
                input,
                llm_chat_history=llm_chat_history,
                lazyllm_files=files,
                stream_output=True,
                **kwargs,
            )
            while True:
                if value := lazyllm.FileSystemQueue().dequeue():
                    yield ''.join(value)
                elif future.done():
                    break
                else:
                    await asyncio.sleep(0.1)
            llm = None

    def forward(self, query, files=None, stream=True, **kwargs: Any) -> Any:
        try:
            lazyllm.LOG.info(f'MODEL_NAME: {self.llm._model_name} GOT QUERY: {query}')
            files = files[:2] if files else None
            llm_chat_history = kwargs.pop('llm_chat_history', [])

            priority = kwargs.pop('priority', 0)
            llm_strategy = kwargs.get('llm_strategy', LlmStrategy(priority=priority))
            if isinstance(llm_strategy, LlmStrategy):
                llm_strategy = llm_strategy.model_dump()

            llm = self.llm.share()
            kw = {k: v for k, v in llm_strategy.items() if v is not None}

            if stream:
                response = self.astream_iterator(
                    input=query,
                    llm=llm,
                    files=files,
                    llm_chat_history=llm_chat_history,
                    **kw,
                )
            else:
                response = llm(
                    query,
                    stream_output=False,
                    llm_chat_history=llm_chat_history,
                    lazyllm_files=files,
                    **kw,
                )
            return response
        except Exception as e:
            lazyllm.LOG.exception(e)
            raise e
        finally:
            llm = None
