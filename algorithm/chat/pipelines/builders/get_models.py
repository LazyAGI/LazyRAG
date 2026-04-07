from __future__ import annotations
import asyncio
import os
import tempfile
import threading
from typing import Any, Dict, List, Optional

import lazyllm
import yaml
from lazyllm import AutoModel, ModuleBase
from lazyllm.components.formatter import FormatterBase
from lazyllm.components.prompter import PrompterBase

from chat.utils.config import CONFIG_PATH

_DEFAULT_LLM_KW: Dict[str, Any] = {
    'temperature': 0.01,
    'max_tokens': 4096,
    'frequency_penalty': 0,
}

_lock = threading.RLock()
_automodel_cfg: Optional[Dict[str, Any]] = None
_lazyrag_meta: Dict[str, Any] = {}
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
        with lazyllm.ThreadPoolExecutor(1) as executor:
            fut = executor.submit(llm, text, history, files, True, **kw)
            while True:
                if v := lazyllm.FileSystemQueue().dequeue():
                    yield ''.join(v)
                elif fut.done():
                    break
                else:
                    await asyncio.sleep(0.1)

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
    global _automodel_cfg, _lazyrag_meta, _lazyllm_yaml_path
    with _lock:
        if _automodel_cfg is None:
            with open(CONFIG_PATH, encoding='utf-8') as f:
                data = yaml.safe_load(f)
            if not isinstance(data, dict):
                raise ValueError(f'{CONFIG_PATH!r} root must be a mapping')
            raw = dict(data)
            lr = raw.pop('lazyrag', None)
            if lr is not None and not isinstance(lr, dict):
                raise ValueError(f'{CONFIG_PATH!r}: key "lazyrag" must be a mapping when present')
            _lazyrag_meta = lr or {}
            _automodel_cfg = raw
            fd, path = tempfile.mkstemp(prefix='lazyrag_', suffix='_automodel.yaml', text=True)
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                yaml.safe_dump(raw, f, allow_unicode=True, sort_keys=False)
            _lazyllm_yaml_path = path
        return _automodel_cfg


def get_automodel(model_name: str, *, wrap_simple_llm: Optional[bool] = None) -> Any:
    with _lock:
        cfg = load_auto_model_yaml()
        if model_name not in cfg:
            raise KeyError(
                f'Unknown model name {model_name!r} in {CONFIG_PATH!r} '
                '(expected a top-level model key other than "lazyrag")'
            )
        if wrap_simple_llm is None:
            spec = _lazyrag_meta.get('simple_llm_wrapper')
            if spec is None:
                wrap = False
            elif isinstance(spec, dict):
                wrap = bool(spec.get(model_name, False))
            elif isinstance(spec, list):
                wrap = model_name in spec
            else:
                raise TypeError(
                    'lazyrag.simple_llm_wrapper must be a dict (model_name -> bool) or a list of model names'
                )
        else:
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
