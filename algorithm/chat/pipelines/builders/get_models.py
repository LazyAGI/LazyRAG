from __future__ import annotations
import asyncio
import os
import threading
import time
from typing import Any, Dict, List, Optional
import lazyllm
import yaml
from lazyllm import AutoModel, ModuleBase
from lazyllm.components.formatter import FormatterBase
from lazyllm.components.prompter import PrompterBase
from chat.config import CONFIG_PATH

_DEFAULT_LLM_KW: Dict[str, Any] = {
    'temperature': 0.01,
    'max_tokens': 4096,
    'frequency_penalty': 0,
}

_lock = threading.RLock()
_automodel_cfg: Optional[Dict[str, Any]] = None
_lazyllm_yaml_path: Optional[str] = None
_base_models: Dict[str, Any] = {}
_wrapped_models: Dict[str, Any] = {}


class _StreamingLlmModule(ModuleBase):
    def __init__(self, llm: Any, return_trace: bool = False):
        super().__init__(return_trace=return_trace)
        self.llm = llm

    @property
    def series(self):
        return 'LlmComponent'

    @property
    def type(self):
        return 'LLM'

    def share(self, prompt: PrompterBase = None, format: FormatterBase = None,
              stream: Optional[bool] = None, history: List[List[str]] = None,
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

    async def _astream(self, text, llm, files, history, **kw):
        loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue()
        done = object()

        def _pump_fsqueue_to_async():
            try:
                with lazyllm.ThreadPoolExecutor(1) as executor:
                    fut = executor.submit(llm, text, history, files, True, **kw)
                    fsq = lazyllm.FileSystemQueue()
                    idle_sleep = 0.002
                    while True:
                        if v := fsq.dequeue():
                            asyncio.run_coroutine_threadsafe(
                                q.put(''.join(v)), loop
                            ).result()
                            continue
                        if fut.done():
                            while v2 := fsq.dequeue():
                                asyncio.run_coroutine_threadsafe(
                                    q.put(''.join(v2)), loop
                                ).result()
                            break
                        time.sleep(idle_sleep)
            except Exception as e:
                asyncio.run_coroutine_threadsafe(
                    q.put(('_exc', e)), loop
                ).result()
            finally:
                asyncio.run_coroutine_threadsafe(q.put(done), loop).result()

        t = threading.Thread(target=_pump_fsqueue_to_async, daemon=True)
        t.start()
        try:
            while True:
                item = await q.get()
                if item is done:
                    break
                if isinstance(item, tuple) and len(item) == 2 and item[0] == '_exc':
                    raise item[1]
                yield item
        finally:
            t.join(timeout=3600.0)

    def forward(self, query, files=None, stream=True, **kwargs: Any) -> Any:
        llm = None
        try:
            lazyllm.LOG.info(f'MODEL_NAME: {self.llm._model_name} GOT QUERY: {query}')
            files = files[:2] if files else None
            hist = kwargs.pop('llm_chat_history', [])
            priority = kwargs.pop('priority', 0)
            strat = kwargs.get('llm_strategy')
            if strat is None:
                raw = {**_DEFAULT_LLM_KW, 'priority': priority}
            else:
                raw = dict(strat)
            kw = {k: v for k, v in raw.items() if v is not None}
            llm = self.llm.share()
            if stream:
                return self._astream(query, llm, files, hist, **kw)
            return llm(query, stream_output=False, llm_chat_history=hist,
                       lazyllm_files=files, **kw)
        except Exception as e:
            lazyllm.LOG.exception(e)
            raise
        finally:
            llm = None


def load_auto_model_yaml() -> Dict[str, Any]:
    global _automodel_cfg, _lazyllm_yaml_path
    with _lock:
        if _automodel_cfg is None:
            with open(CONFIG_PATH, encoding='utf-8') as f:
                data = yaml.safe_load(f)
            if not isinstance(data, dict):
                raise ValueError(f'{CONFIG_PATH!r} root must be a mapping')
            _automodel_cfg = dict(data)
            _lazyllm_yaml_path = os.path.abspath(CONFIG_PATH)
        return _automodel_cfg


def get_automodel(model_name: str, *, wrap_simple_llm: bool = False) -> Any:
    with _lock:
        cfg = load_auto_model_yaml()
        if model_name not in cfg:
            raise KeyError(
                f'Unknown model name {model_name!r} in {CONFIG_PATH!r} '
                '(expected a top-level model key)'
            )
        wrap = wrap_simple_llm
        if model_name not in _base_models:
            _base_models[model_name] = AutoModel(
                model=model_name,
                config=_lazyllm_yaml_path,
            )
        base = _base_models[model_name]
        if not wrap:
            return base
        if model_name not in _wrapped_models:
            _wrapped_models[model_name] = _StreamingLlmModule(llm=base)
        return _wrapped_models[model_name]
