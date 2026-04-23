"""Concurrency tests for ``chat.pipelines.agentic_v2``.

Verify that when multiple requests run in parallel — either via OS threads
(sync path) or asyncio tasks driving the streaming generator — each request's
``agentic_config`` is isolated, and the tools invoked inside each request
observe their own per-request configuration without cross-contamination.

The design relies on ``lazyllm.globals`` being keyed by a per-session id
(SID). Production code in ``chat_service.handle_chat`` calls
``lazyllm.globals._init_sid(sid=session_id)`` before running the pipeline so
every incoming request lands in its own SID bucket. These tests exercise
exactly that contract for both the sync and streaming entry points.
"""
from __future__ import annotations

import asyncio
import threading
import time
from typing import Any, Dict, List

import pytest
import lazyllm

from chat.pipelines import agentic_v2


class _FakeAgent:
    """Fake ReactAgent that records the ``agentic_config`` visible at call time.

    Instances capture whatever kwargs the pipeline uses to build a real
    ``ReactAgent`` (``prompt``, ``tools``, ``skills``, ...), and when invoked
    they simulate a tool-call round that reads ``lazyllm.globals`` to retrieve
    the per-request config — mirroring what real tools like ``kb_search`` do.
    """

    _lock = threading.Lock()
    observations: List[Dict[str, Any]] = []

    def __init__(self, **kwargs: Any) -> None:
        self._kwargs = kwargs

    def __call__(self, query: str, llm_chat_history: Any = None) -> Dict[str, Any]:
        time.sleep(0.05)
        config = lazyllm.globals.get('agentic_config')
        snapshot = dict(config) if isinstance(config, dict) else None
        callback = self._kwargs.get('stream_event_callback')
        if callable(callback):
            callback({
                'round': 1,
                'content': f'observed:{snapshot.get("kb_name") if snapshot else None}',
                'tool_calls': [],
            })
        with type(self)._lock:
            type(self).observations.append({
                'query': query,
                'sid': lazyllm.globals._sid,
                'config': snapshot,
                'agent_kwargs_prompt': self._kwargs.get('prompt'),
                'agent_kwargs_tools': tuple(self._kwargs.get('tools') or ()),
            })
        return {
            'query': query,
            'observed_kb_name': snapshot.get('kb_name') if snapshot else None,
        }


@pytest.fixture
def fake_pipeline(monkeypatch):
    """Patch agentic_v2's heavy external deps so it can run offline."""
    _FakeAgent.observations = []

    monkeypatch.setattr(agentic_v2, 'get_automodel', lambda *_a, **_kw: object())
    monkeypatch.setattr(agentic_v2, 'create_sandbox', lambda **_kw: object())
    monkeypatch.setattr(
        agentic_v2, 'list_all_skills_with_category', lambda *_a, **_kw: {}
    )
    monkeypatch.setattr(agentic_v2, '_ensure_tools_registered', lambda: None)
    monkeypatch.setattr(agentic_v2, '_spawn_background_review', lambda **_kw: None)
    monkeypatch.setattr(agentic_v2, '_get_runtime_agent_defaults', lambda: {})
    monkeypatch.setattr(agentic_v2, '_StreamingReactAgent', _FakeAgent)
    monkeypatch.setattr(lazyllm.tools.agent, 'ReactAgent', _FakeAgent)

    yield _FakeAgent


def _build_configs(prefix: str, n: int) -> List[Dict[str, Any]]:
    return [
        {
            'query': f'{prefix}{i}',
            'kb_name': f'{prefix}kb_{i}',
            'kb_id': f'{prefix}id_{i}',
            'kb_url': f'http://{prefix}host/{i}',
            'available_tools': [f'tool_{prefix}{i}'],
        }
        for i in range(n)
    ]


def test_thread_parallel_requests_see_isolated_config(fake_pipeline):
    """Each OS-thread request gets its own ``agentic_config`` snapshot."""
    n = 8
    configs = _build_configs('t_', n)
    results: List[Any] = [None] * n
    barrier = threading.Barrier(n)

    def _run(i: int) -> None:
        lazyllm.globals._init_sid(sid=f'sync-session-{i}')
        lazyllm.locals._init_sid(sid=f'sync-session-{i}')
        barrier.wait()
        results[i] = agentic_v2.agentic_rag_v2(configs[i], stream=False)

    threads = [threading.Thread(target=_run, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(fake_pipeline.observations) == n
    obs_by_query = {obs['query']: obs for obs in fake_pipeline.observations}
    assert set(obs_by_query.keys()) == {f't_{i}' for i in range(n)}

    sids = set()
    for i in range(n):
        obs = obs_by_query[f't_{i}']
        sids.add(obs['sid'])
        assert obs['sid'] == f'sync-session-{i}'
        assert obs['config']['kb_name'] == f't_kb_{i}'
        assert obs['config']['kb_id'] == f't_id_{i}'
        assert obs['config']['kb_url'] == f'http://t_host/{i}'
        assert obs['agent_kwargs_tools'] == (f'tool_t_{i}',)
        assert results[i]['observed_kb_name'] == f't_kb_{i}'

    assert len(sids) == n, f'threads should get distinct SIDs, got {sids!r}'


def test_stream_parallel_requests_see_isolated_config(fake_pipeline):
    """Each asyncio-task streaming request observes only its own config.

    The streaming path spawns a dedicated worker thread per request and
    re-initialises the SID inside it so the worker shares the caller's
    ``agentic_config``. This guards that wiring against regressions.
    """
    n = 6

    async def _drive():
        async def _one(i: int):
            # Mirror chat_service.handle_chat: every incoming request first
            # pins its own SID so globals writes land in an isolated bucket.
            session_id = f'stream-session-{i}'
            lazyllm.globals._init_sid(sid=session_id)
            lazyllm.locals._init_sid(sid=session_id)
            params = {
                'query': f's_{i}',
                'kb_name': f's_kb_{i}',
                'kb_id': f's_id_{i}',
                'kb_url': f'http://s_host/{i}',
                'available_tools': [f's_tool_{i}'],
            }
            stream = agentic_v2.agentic_rag_v2(params, stream=True)
            events = []
            async for event in stream:
                events.append(event)
            outer = lazyllm.globals.get('agentic_config')
            return events, outer, session_id

        tasks = [asyncio.create_task(_one(i)) for i in range(n)]
        return await asyncio.gather(*tasks)

    results = asyncio.run(_drive())

    assert len(fake_pipeline.observations) == n
    obs_by_query = {obs['query']: obs for obs in fake_pipeline.observations}
    assert set(obs_by_query.keys()) == {f's_{i}' for i in range(n)}

    for i in range(n):
        obs = obs_by_query[f's_{i}']
        assert obs['sid'] == f'stream-session-{i}'
        assert obs['config']['kb_name'] == f's_kb_{i}'
        assert obs['config']['kb_id'] == f's_id_{i}'
        assert obs['config']['kb_url'] == f'http://s_host/{i}'
        assert obs['agent_kwargs_tools'] == (f's_tool_{i}',)

    for i, (events, outer, session_id) in enumerate(results):
        assert session_id == f'stream-session-{i}'
        assert isinstance(outer, dict)
        assert outer.get('kb_name') == f's_kb_{i}', (
            'the asyncio task should still see its own agentic_config after '
            'the streaming worker finishes'
        )
