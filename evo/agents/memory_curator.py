from __future__ import annotations
from typing import Any
from evo.conductor.prompts import load as load_prompt
from evo.harness.react import LLMInvoker
from evo.runtime.session import AnalysisSession

CURATOR_NAME = 'memory_curator'
_MAX_MEMORY_CHARS = 2000


class MemoryCurator:
    def __init__(self, session: AnalysisSession, agent: str, llm: Any | None = None) -> None:
        self.session = session
        self.agent = agent
        self.invoker = LLMInvoker(session=session, system_prompt=load_prompt('memory_curator'), llm=llm)

    def update(
        self, working_memory: str, *, tool: str, args_brief: str, summary: str, handle: str | None, ok: bool
    ) -> str:
        user = (
            f"当前 working_memory:\n{working_memory or '(empty)'}\n\n"
            f'最新一次工具调用:\n- tool: {tool}\n'
            f"- args: {args_brief or '(none)'}\n"
            f'- summary: {summary}\n'
            f"- handle: {handle or '(none)'}\n"
            f'- ok: {str(ok).lower()}\n'
        )
        raw = self.session.llm.call(
            producer=lambda: self.invoker.invoke(user),
            cache_key=None,
            use_cache=False,
            agent=f'{CURATOR_NAME}:{self.agent}',
        )
        text = (raw or '').strip()
        if not text:
            return working_memory
        return text[:_MAX_MEMORY_CHARS]
