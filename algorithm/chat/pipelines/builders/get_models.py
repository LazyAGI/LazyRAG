from __future__ import annotations

import asyncio
import atexit
import functools
import hashlib
import os
import re
import shutil
import tempfile
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
import lazyllm
from lazyllm import AutoModel, ModuleBase
from lazyllm.components.formatter import FormatterBase
from lazyllm.components.prompter import PrompterBase

from chat.utils.load_config import get_role_config

_RUNTIME_AUTO_MODEL_DIR = Path(tempfile.gettempdir()) / 'lazyrag-runtime-auto-model'

_DEFAULT_LLM_KW: Dict[str, Any] = {
    'temperature': 0.01,
    'max_tokens': 4096,
    'frequency_penalty': 0,
}

_lock = threading.RLock()
_base_models: Dict[str, Any] = {}
_wrapped_models: Dict[str, Any] = {}


def _cleanup_runtime_auto_model_dir() -> None:
    shutil.rmtree(_RUNTIME_AUTO_MODEL_DIR, ignore_errors=True)


atexit.register(_cleanup_runtime_auto_model_dir)


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
              copy_static_params: bool = False):
        self.llm = self.llm.share(
            prompt=prompt, format=format, stream=stream,
            history=history, copy_static_params=copy_static_params,
        )
        return self

    async def _astream(self, text, llm, files, history, **kw):
        with lazyllm.ThreadPoolExecutor(1) as executor:
            future = executor.submit(
                llm, text,
                llm_chat_history=history,
                lazyllm_files=files,
                stream_output=True,
                **kw,
            )
            while True:
                if value := lazyllm.FileSystemQueue().dequeue():
                    yield ''.join(value)
                elif future.done():
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
            raw = {**_DEFAULT_LLM_KW, 'priority': priority} if strat is None else dict(strat)
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


@functools.lru_cache(maxsize=64)
def _write_auto_model_config(serialized_config: str) -> str:
    config = yaml.safe_load(serialized_config)
    model_name = config['model']
    digest = hashlib.sha256(serialized_config.encode('utf-8')).hexdigest()[:16]
    safe_name = re.sub(r'[^A-Za-z0-9_.-]+', '-', model_name).strip('-') or 'model'
    _RUNTIME_AUTO_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    config_path = _RUNTIME_AUTO_MODEL_DIR / f'{safe_name}-{digest}.yaml'
    temp_fd, temp_path = tempfile.mkstemp(
        dir=_RUNTIME_AUTO_MODEL_DIR, prefix=f'.{safe_name}-{digest}-', suffix='.yaml',
    )
    try:
        with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
            yaml.safe_dump({model_name: [config]}, f, sort_keys=False)
        os.replace(temp_path, config_path)
    except Exception:
        try:
            os.unlink(temp_path)
        except FileNotFoundError:
            pass
        raise
    return str(config_path)


def _build_auto_model(model_name: str, config: Dict[str, Any]):
    cfg = deepcopy(config)
    cfg['model'] = model_name
    serialized = yaml.safe_dump(cfg, sort_keys=True)
    return AutoModel(model=model_name, config=_write_auto_model_config(serialized))


def get_automodel(role: str, *, wrap_simple_llm: bool = False) -> Any:
    with _lock:
        if role not in _base_models:
            model_name, config = get_role_config(role)
            _base_models[role] = _build_auto_model(model_name, config)
        base = _base_models[role]
        if not wrap_simple_llm:
            return base
        if role not in _wrapped_models:
            _wrapped_models[role] = _StreamingLlmModule(llm=base)
        return _wrapped_models[role]
