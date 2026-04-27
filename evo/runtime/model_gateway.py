from __future__ import annotations

import concurrent.futures as _cf
import contextvars
import logging
import threading
import time
from collections import OrderedDict
from typing import Callable, Generic, TypeVar

from evo.runtime.config import ModelGovernanceConfig

T = TypeVar('T')

_TIMEOUT_EXEC = _cf.ThreadPoolExecutor(max_workers=8, thread_name_prefix='evo-mg')


class TokenBucket:
    def __init__(self, rate: float, burst: int) -> None:
        self._rate = rate
        self._burst = burst
        self._tokens = float(burst)
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self, timeout: float = 30.0) -> None:
        deadline = time.monotonic() + timeout
        while True:
            with self._lock:
                now = time.monotonic()
                self._tokens = min(self._burst, self._tokens + (now - self._last) * self._rate)
                self._last = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
            if time.monotonic() >= deadline:
                raise TimeoutError('Model gateway rate limiter timed out')
            time.sleep(0.05)


class ModelGateway(Generic[T]):
    def __init__(
        self,
        cfg: ModelGovernanceConfig,
        *,
        name: str = 'model',
        logger: logging.Logger | None = None,
        on_event: Callable[..., None] | None = None,
    ) -> None:
        self._cfg = cfg
        self._bucket = TokenBucket(cfg.rate_limit_per_sec, cfg.burst)
        self._cache: OrderedDict[str, T] = OrderedDict()
        self._cache_lock = threading.Lock()
        self._log = logger or logging.getLogger(f'evo.{name}')
        self._name = name
        self._disabled = False
        self._on_event = on_event or (lambda *a, **kw: None)

    @property
    def is_disabled(self) -> bool:
        return self._disabled

    def acquire_slot(self) -> None:
        self._bucket.acquire()

    def _cache_get(self, key: str) -> T | None:
        with self._cache_lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
        return None

    def _cache_put(self, key: str, value: T) -> None:
        with self._cache_lock:
            self._cache[key] = value
            self._cache.move_to_end(key)
            while len(self._cache) > self._cfg.cache_size:
                self._cache.popitem(last=False)

    def _run_with_timeout(self, producer: Callable[[], T]) -> T:
        timeout = self._cfg.producer_timeout_s
        if not timeout or timeout <= 0:
            return producer()
        ctx = contextvars.copy_context()
        future = _TIMEOUT_EXEC.submit(ctx.run, producer)
        try:
            return future.result(timeout=timeout)
        except _cf.TimeoutError as exc:
            future.cancel()
            raise TimeoutError(
                f'{self._name} producer exceeded {timeout:g}s'
            ) from exc

    def call(
        self,
        producer: Callable[[], T],
        *,
        cache_key: str | None = None,
        use_cache: bool | None = None,
        agent: str = '',
    ) -> T | None:
        if self._disabled:
            self._on_event('llm_call', gateway=self._name, agent=agent,
                           ok=False, disabled=True, attempts=0,
                           cache_hit=False, elapsed_s=0.0)
            return None
        use_cache = self._cfg.use_cache if use_cache is None else use_cache
        if use_cache and cache_key:
            hit = self._cache_get(cache_key)
            if hit is not None:
                self._log.info('%s cache hit', self._name)
                self._on_event('llm_call', gateway=self._name, agent=agent,
                               ok=True, cache_hit=True, attempts=0, elapsed_s=0.0)
                return hit

        last_exc: Exception | None = None
        t_start = time.monotonic()
        for attempt in range(1, self._cfg.max_retries + 1):
            try:
                self._bucket.acquire()
                t0 = time.monotonic()
                out = self._run_with_timeout(producer)
                elapsed = time.monotonic() - t0
                self._log.info('%s ok attempt=%d in %.2fs', self._name, attempt, elapsed)
                if use_cache and cache_key:
                    self._cache_put(cache_key, out)
                self._on_event('llm_call', gateway=self._name, agent=agent,
                               ok=True, cache_hit=False, attempts=attempt,
                               elapsed_s=round(time.monotonic() - t_start, 4))
                return out
            except Exception as exc:
                last_exc = exc
                if attempt < self._cfg.max_retries:
                    delay = self._cfg.retry_base_seconds * 2 ** (attempt - 1)
                    self._log.warning('%s attempt %d failed (%s); retrying in %.1fs',
                                      self._name, attempt, exc, delay)
                    time.sleep(delay)

        assert last_exc is not None
        self._on_event('llm_call', gateway=self._name, agent=agent,
                       ok=False, cache_hit=False, attempts=self._cfg.max_retries,
                       elapsed_s=round(time.monotonic() - t_start, 4),
                       error=type(last_exc).__name__)
        if self._cfg.on_failure == 'disable':
            self._log.warning('%s disabled after %d failures: %s',
                              self._name, self._cfg.max_retries, last_exc)
            self._disabled = True
            return None
        raise last_exc


__all__ = ['ModelGateway', 'ModelGovernanceConfig', 'TokenBucket']
