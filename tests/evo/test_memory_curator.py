"""Phase 5 tests for MemoryCurator + ReActRunner working_memory integration.

Run: PYTHONPATH=. .venv/bin/python -m evo.tests.test_memory_curator
"""

from __future__ import annotations

import sys
import traceback
from typing import Callable
from unittest.mock import MagicMock, patch

from evo.agents.memory_curator import MemoryCurator, _MAX_MEMORY_CHARS
from evo.harness.react import ReActConfig, ReActRunner, _Turn
from evo.runtime.config import load_config
from evo.runtime.session import create_session, session_scope


def _h(name: str) -> None:
    print(f"\n=== {name} ===")


def test_curator_caps_output_at_2000_chars() -> None:
    _h("MemoryCurator: oversized LLM output is truncated to 2000 chars")
    session = create_session(load_config())
    with session_scope(session):
        with patch("evo.agents.memory_curator.LLMInvoker") as MockInvoker:
            MockInvoker.return_value.invoke.return_value = "x" * 5000
            curator = MemoryCurator(session, agent="trace")
            out = curator.update(
                "(empty)", tool="t", args_brief="", summary="s",
                handle="h_0001", ok=True,
            )
    assert len(out) == _MAX_MEMORY_CHARS == 2000
    print("  -> OK")


def test_curator_empty_response_keeps_old_memory() -> None:
    _h("MemoryCurator: empty LLM response leaves working_memory unchanged")
    session = create_session(load_config())
    with session_scope(session):
        with patch("evo.agents.memory_curator.LLMInvoker") as MockInvoker:
            MockInvoker.return_value.invoke.return_value = ""
            curator = MemoryCurator(session, agent="trace")
            old = "## 已确认事实\n- [h_0001] foo"
            out = curator.update(
                old, tool="t", args_brief="", summary="s",
                handle=None, ok=True,
            )
    assert out == old
    print("  -> OK")


def test_curator_returns_llm_markdown() -> None:
    _h("MemoryCurator: returns LLM markdown verbatim when within size limit")
    session = create_session(load_config())
    fake_md = (
        "## 已确认事实\n- [h_0001] step Retriever_2 chunk_recall=0\n\n"
        "## 待验证假设\n- [ ] H1: ...\n\n"
        "## 还需要查\n- inspect_step_for_case\n\n"
        "## 已用工具\nsummarize_step_metrics(1)"
    )
    with session_scope(session):
        with patch("evo.agents.memory_curator.LLMInvoker") as MockInvoker:
            MockInvoker.return_value.invoke.return_value = fake_md
            curator = MemoryCurator(session, agent="trace")
            out = curator.update(
                "", tool="summarize_step_metrics", args_brief="",
                summary="lowest mean: ...", handle="h_0001", ok=True,
            )
    assert out == fake_md
    print("  -> OK")


def test_runner_threads_working_memory_into_prompt() -> None:
    _h("ReActRunner: working_memory replaces observed_facts and appears in prompt")
    session = create_session(load_config())
    with session_scope(session):
        invoker = MagicMock()
        invoker.invoke.side_effect = [
            'Thought: x\nAction: summarize_metrics\nAction Input: {}',
            "FINAL_JSON",
        ]
        runner = ReActRunner(
            session=session, tool_names=["summarize_metrics"], invoker=invoker,
            cfg=ReActConfig(max_rounds=5, min_tool_calls=0, use_memory_curator=True),
        )
        with patch("evo.agents.memory_curator.MemoryCurator.update",
                   return_value="## 已确认事实\n- [h_0001] DEMO FACT\n## 待验证假设\n## 还需要查\n## 已用工具"):
            from evo.tools import register_all
            register_all()
            from evo.harness import data_loader
            data_loader.load_corpus(session)
            runner.run("t")
    second_prompt = invoker.invoke.call_args_list[1][0][0]
    assert "## 当前已知" in second_prompt
    assert "DEMO FACT" in second_prompt
    assert "## 已观察事实" not in second_prompt
    print("  -> OK")


def test_runner_disable_curator() -> None:
    _h("ReActRunner: use_memory_curator=False -> no working_memory section")
    session = create_session(load_config())
    with session_scope(session):
        invoker = MagicMock()
        invoker.invoke.side_effect = [
            'Thought: x\nAction: summarize_metrics\nAction Input: {}',
            "FINAL",
        ]
        runner = ReActRunner(
            session=session, tool_names=["summarize_metrics"], invoker=invoker,
            cfg=ReActConfig(max_rounds=5, min_tool_calls=0, use_memory_curator=False),
        )
        from evo.tools import register_all
        register_all()
        from evo.harness import data_loader
        data_loader.load_corpus(session)
        runner.run("t")
    second_prompt = invoker.invoke.call_args_list[1][0][0]
    assert "## 当前已知" not in second_prompt
    print("  -> OK")


def _run(tests: list[Callable[[], None]]) -> int:
    failures = 0
    for t in tests:
        try:
            t()
        except Exception:
            failures += 1
            print(f"FAILED: {t.__name__}")
            traceback.print_exc(limit=5)
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    return 0 if failures == 0 else 1


def main() -> int:
    return _run([
        test_curator_caps_output_at_2000_chars,
        test_curator_empty_response_keeps_old_memory,
        test_curator_returns_llm_markdown,
        test_runner_threads_working_memory_into_prompt,
        test_runner_disable_curator,
    ])


if __name__ == "__main__":
    sys.exit(main())
