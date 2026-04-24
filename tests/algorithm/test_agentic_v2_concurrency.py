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
                'agent_kwargs_skills': tuple(self._kwargs.get('skills') or ()),
                'agent_kwargs_max_retries': self._kwargs.get('max_retries'),
                'agent_kwargs_force_summarize': self._kwargs.get('force_summarize'),
                'agent_kwargs_force_summarize_context': self._kwargs.get('force_summarize_context'),
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
            'available_skills': [f'skill_{prefix}{i}'],
            'skill_fs_url': f'file:///tmp/{prefix}skills/{i}',
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
        assert obs['config']['available_skills'] == [f'skill_t_{i}']
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
                'available_skills': [f's_skill_{i}'],
                'skill_fs_url': f'file:///tmp/stream-skills/{i}',
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
        assert obs['config']['available_skills'] == [f's_skill_{i}']

    for i, (events, outer, session_id) in enumerate(results):
        assert session_id == f'stream-session-{i}'
        assert isinstance(outer, dict)
        assert outer.get('kb_name') == f's_kb_{i}', (
            'the asyncio task should still see its own agentic_config after '
            'the streaming worker finishes'
        )


def test_kb_tools_disabled_without_kb_id_or_files(fake_pipeline):
    lazyllm.globals._init_sid(sid='no-kb-session')
    lazyllm.locals._init_sid(sid='no-kb-session')

    agentic_v2.agentic_rag_v2({
        'query': 'hello',
        'available_tools': ['all'],
        'filters': {},
        'files': [],
    })

    assert fake_pipeline.observations[-1]['agent_kwargs_tools'] == (
        'memory',
        'skill_manage',
    )


def test_single_file_request_keeps_temp_file_search_only(fake_pipeline):
    lazyllm.globals._init_sid(sid='file-session')
    lazyllm.locals._init_sid(sid='file-session')

    agentic_v2.agentic_rag_v2({
        'query': 'summarize this file',
        'available_tools': ['all'],
        'filters': {},
        'files': ['/var/lib/lazyrag/uploads/a.pdf'],
    })

    obs = fake_pipeline.observations[-1]
    assert obs['config']['temp_files'] == ['/var/lib/lazyrag/uploads/a.pdf']
    assert obs['agent_kwargs_tools'] == (
        'kb_search',
        'memory',
        'skill_manage',
    )


def test_tool_stream_frame_serializes_tool_call_into_text_tags():
    frame = agentic_v2._format_tool_stream_frame({
        'round': 3,
        'content': (
            '<think>参考文件不存在。让我检查一下skill目录中实际有哪些文件。\n'
            '</think>\n\n让我查看技能目录中有哪些可用的参考文件：\n'
        ),
        'tool_calls': [{
            'id': 'toolcall-3-1',
            'name': 'run_script',
            'arguments': {
                'name': 'railway-foundation-bearing-capacity-review',
                'rel_path': 'scripts/list_files.sh',
            },
        }],
    })

    assert frame == {
        'think': None,
        'text': (
            '<tp id="toolcall-3-1">正在运行现成的辅助脚本：scripts/list_files.sh</tp>'
            '<tool_call>{"id":"toolcall-3-1","name":"run_script","arguments":{"name":"railway-foundation-bearing-capacity-review","rel_path":"scripts/list_files.sh"}}</tool_call>'
        ),
        'sources': [],
    }


def test_tool_stream_frame_uses_representative_kb_arguments():
    frame = agentic_v2._format_tool_stream_frame({
        'round': 1,
        'content': '',
        'tool_calls': [
            {
                'id': 'toolcall-1-1',
                'name': 'kb_search',
                'arguments': {
                    'query': '全风化 软岩 风化岩分组 地基承载力 σ0 表',
                    'topk': 15,
                },
            },
            {
                'id': 'toolcall-1-2',
                'name': 'kb_get_window_nodes',
                'arguments': {
                    'docid': 'doc_7e052315556b40323f5007c5b9f549ab',
                    'number': '36',
                    'group': 'block',
                },
            },
        ],
    })

    assert frame == {
        'think': None,
        'text': (
            '<tp id="toolcall-1-1">正在知识库中查找全风化 软岩 风化岩分组 地基承载力 σ0 表相关资料</tp>'
            '<tool_call>{"id":"toolcall-1-1","name":"kb_search","arguments":{"query":"全风化 软岩 风化岩分组 地基承载力 σ0 表","topk":15}}</tool_call>'
            '<tp id="toolcall-1-2">正在展开相关片段：36</tp>'
            '<tool_call>{"id":"toolcall-1-2","name":"kb_get_window_nodes","arguments":{"docid":"doc_7e052315556b40323f5007c5b9f549ab","number":"36","group":"block"}}</tool_call>'
        ),
        'sources': [],
    }


def test_tool_stream_frame_serializes_full_tool_result_into_text_tags():
    frame = agentic_v2._format_tool_stream_frame({
        'round': 2,
        'content': '',
        'tool_results': [{
            'id': 'toolcall-2-1',
            'tool_name': 'memory',
            'result': {
                'status': 'success',
                'message': 'memory saved',
                'path': '/tmp/memory.json',
            },
        }],
    })

    assert frame == {
        'think': None,
        'text': (
            '<trp id="toolcall-2-1">已记录这条信息：memory saved</trp>'
            '<tool_result>{"id":"toolcall-2-1","name":"memory","result":{"status":"success","message":"memory saved","path":"/tmp/memory.json"}}</tool_result>'
        ),
        'sources': [],
    }


def test_builtin_file_tool_uses_natural_preview_templates():
    frame = agentic_v2._format_tool_stream_frame({
        'round': 4,
        'content': '',
        'tool_calls': [{
            'id': 'toolcall-4-1',
            'name': 'read_file',
            'arguments': {
                'path': '/tmp/demo.txt',
                'start_line': 1,
                'end_line': 20,
            },
        }],
        'tool_results': [{
            'id': 'toolcall-4-1',
            'tool_name': 'read_file',
            'result': {
                'status': 'ok',
                'path': '/tmp/demo.txt',
                'content': 'hello world',
            },
        }],
    })

    assert frame == {
        'think': None,
        'text': (
            '<tp id="toolcall-4-1">正在查看文件内容：/tmp/demo.txt</tp>'
            '<tool_call>{"id":"toolcall-4-1","name":"read_file","arguments":{"path":"/tmp/demo.txt","start_line":1,"end_line":20}}</tool_call>'
            '<trp id="toolcall-4-1">已读取文件内容：hello world</trp>'
            '<tool_result>{"id":"toolcall-4-1","name":"read_file","result":{"status":"ok","path":"/tmp/demo.txt","content":"hello world"}}</tool_result>'
        ),
        'sources': [],
    }


def test_tool_result_preview_is_truncated_to_fifty_chars():
    long_result = 'a' * 60

    frame = agentic_v2._format_tool_stream_frame({
        'round': 5,
        'content': '',
        'tool_results': [{
            'id': 'toolcall-5-1',
            'tool_name': 'read_file',
            'result': {
                'status': 'ok',
                'path': '/tmp/long.txt',
                'content': long_result,
            },
        }],
    })

    assert frame == {
        'think': None,
        'text': (
            '<trp id="toolcall-5-1">已读取文件内容：'
            'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa...</trp>'
            '<tool_result>{"id":"toolcall-5-1","name":"read_file","result":{"status":"ok","path":"/tmp/long.txt","content":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}}</tool_result>'
        ),
        'sources': [],
    }


def test_tool_result_failure_uses_failure_preview_template():
    frame = agentic_v2._format_tool_stream_frame({
        'round': 6,
        'content': '',
        'tool_results': [{
            'id': 'toolcall-6-1',
            'tool_name': 'read_file',
            'result': {
                'status': 'missing',
                'path': '/tmp/missing.txt',
            },
        }],
    })

    assert frame == {
        'think': None,
        'text': (
            '<trp id="toolcall-6-1">暂时没能读取文件内容：/tmp/missing.txt</trp>'
            '<tool_result>{"id":"toolcall-6-1","name":"read_file","result":{"status":"missing","path":"/tmp/missing.txt"}}</tool_result>'
        ),
        'sources': [],
    }


def test_tool_result_needs_approval_uses_approval_preview_template():
    frame = agentic_v2._format_tool_stream_frame({
        'round': 7,
        'content': '',
        'tool_results': [{
            'id': 'toolcall-7-1',
            'tool_name': 'delete_file',
            'result': {
                'status': 'needs_approval',
                'reason': 'Deleting files requires approval.',
                'path': '/tmp/demo.txt',
            },
        }],
    })

    assert frame == {
        'think': None,
        'text': (
            '<trp id="toolcall-7-1">删除文件前还需要进一步确认：Deleting files requires approval.</trp>'
            '<tool_result>{"id":"toolcall-7-1","name":"delete_file","result":{"status":"needs_approval","reason":"Deleting files requires approval.","path":"/tmp/demo.txt"}}</tool_result>'
        ),
        'sources': [],
    }


def test_normalize_history_keeps_plain_chat_messages_unchanged():
    history = [
        {'role': 'user', 'content': 'hello'},
        {'role': 'assistant', 'content': 'world'},
    ]

    assert agentic_v2._normalize_history_for_agent(history) == history


def test_normalize_history_rebuilds_tool_messages_from_assistant_content():
    history = [{
        'role': 'assistant',
        'content': (
            '先看文件。'
            '<tp id="toolcall-1-1">正在查看文件内容：/tmp/demo.txt</tp>'
            '<tool_call>{"id":"toolcall-1-1","name":"read_file","arguments":{"path":"/tmp/demo.txt"}}</tool_call>'
            '<trp id="toolcall-1-1">已读取文件内容：hello world</trp>'
            '<tool_result>{"id":"toolcall-1-1","name":"read_file","result":{"status":"ok","content":"hello world"}}</tool_result>'
        ),
    }]

    assert agentic_v2._normalize_history_for_agent(history) == [
        {
            'role': 'assistant',
            'content': '先看文件。',
            'tool_calls': [{
                'id': 'toolcall-1-1',
                'function': {
                    'name': 'read_file',
                    'arguments': '{"path":"/tmp/demo.txt"}',
                },
            }],
        },
        {
            'role': 'tool',
            'tool_call_id': 'toolcall-1-1',
            'name': 'read_file',
            'content': '{"status":"ok","content":"hello world"}',
        },
    ]


def test_review_debug_forces_combined(monkeypatch):
    monkeypatch.setenv('LAZYRAG_SKILL_REVIEW_DEBUG', 'TRUE')

    assert agentic_v2._decide_review_mode(
        available_tools=[],
        tool_turns=0,
        user_turns=0,
        memory_review_interval=99,
        skill_review_interval=99,
    ) == 'combined'


def test_review_mode_uses_intervals_without_debug(monkeypatch):
    monkeypatch.delenv('LAZYRAG_SKILL_REVIEW_DEBUG', raising=False)

    assert agentic_v2._decide_review_mode(
        available_tools=['memory', 'skill_manage'],
        tool_turns=0,
        user_turns=2,
        memory_review_interval=1,
        skill_review_interval=5,
    ) == 'memory'


def test_count_tool_turns_only_counts_assistant_messages_with_tool_calls():
    history = agentic_v2._normalize_history_for_agent([
        {'role': 'assistant', 'content': 'plain text'},
        {
            'role': 'assistant',
            'content': (
                '<tool_call>{"id":"call-1","name":"kb_search","arguments":{"query":"foo"}}</tool_call>'
                '<tool_result>{"id":"call-1","name":"kb_search","result":{"total":1}}</tool_result>'
            ),
        },
        {
            'role': 'assistant',
            'content': (
                'done'
                '<tool_call>{"id":"call-2","name":"memory","arguments":{"target":"memory"}}</tool_call>'
                '<tool_result>{"id":"call-2","name":"memory","result":{"status":"ok"}}</tool_result>'
            ),
        },
    ])

    assert agentic_v2._count_tool_turns(history) == 2


def test_spawn_background_review_uses_all_skills_under_skill_fs_url(monkeypatch):
    captured = {}

    class _ReviewAgent:
        def __init__(self, **kwargs):
            captured['skills'] = tuple(kwargs.get('skills') or ())
            captured['skills_dir'] = kwargs.get('skills_dir')

        def __call__(self, *_args, **_kwargs):
            return 'ok'

    monkeypatch.setattr(
        agentic_v2,
        'list_all_skills_with_category',
        lambda _path: {
            'skill_a': '',
            'skill_b': 'ops',
            'skill_c': 'drafts',
        },
    )
    monkeypatch.setattr(lazyllm.tools.agent, 'ReactAgent', _ReviewAgent)
    monkeypatch.setenv('LAZYRAG_REVIEW_DEBUG', '1')

    agentic_v2._spawn_background_review(
        config={
            'available_skills': ['skill_a'],
            'skill_fs_url': 'file:///tmp/skills',
        },
        llm=object(),
        sandbox=object(),
        keep_full_turns=3,
        history_snapshot=[],
        review_mode='skill',
        request_global_sid='sid-review',
    )

    assert captured == {
        'skills': ('skill_a', 'skill_b', 'skill_c'),
        'skills_dir': 'file:///tmp/skills',
    }


def test_max_retries_and_force_summary_use_lazyrag_env(fake_pipeline, monkeypatch):
    monkeypatch.setenv('LAZYRAG_MAX_RETRIES', '13')
    lazyllm.globals._init_sid(sid='max-retries-session')
    lazyllm.locals._init_sid(sid='max-retries-session')

    agentic_v2.agentic_rag_v2({
        'query': 'hello',
        'available_tools': [],
    })

    obs = fake_pipeline.observations[-1]
    assert obs['agent_kwargs_max_retries'] == 13
    assert obs['agent_kwargs_force_summarize'] is True
    assert obs['agent_kwargs_force_summarize_context'] == 'hello'
