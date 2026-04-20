from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any

from evo.domain.tool_result import ErrorCode, ToolResult
from evo.harness.registry import ToolSpec, get_registry
from evo.runtime.session import AnalysisSession

_REACT_FORMAT = """\
## 工具调用格式
需要使用工具时，严格使用以下格式（每次只调用一个工具）:

Thought: <你的思考>
Action: <工具名>
Action Input: <JSON 参数>

系统会返回:
Observation: <结果>

收集到足够证据后，直接输出最终 JSON 结果（不要再写 Action）。"""


@dataclass
class ReActConfig:
    max_rounds: int = 10
    max_observation_chars: int = 40000
    window_turns: int = 4
    same_streak_warn: int = 2
    fail_streak_warn: int = 2
    min_tool_calls: int = 0
    required_tools: tuple[str, ...] = ()
    max_finish_warnings: int = 2
    use_memory_curator: bool = True


@dataclass
class ReActStats:
    rounds: int = 0
    tool_calls: dict[str, int] = None  # type: ignore[assignment]
    same_streak_hits: int = 0
    fail_streak_hits: int = 0
    finish_warnings: int = 0

    def __post_init__(self) -> None:
        if self.tool_calls is None:
            self.tool_calls = {}

    @property
    def total_tool_calls(self) -> int:
        return sum(self.tool_calls.values())

    @property
    def distinct_tools(self) -> int:
        return len(self.tool_calls)


@dataclass
class _Turn:
    response: str
    tool: str
    args: dict[str, Any]
    obs: str
    ok: bool
    summary: str   # one-line summarizer output for sliding-window history


def _format_tools(specs: list[ToolSpec]) -> str:
    return "\n".join(spec.describe() for spec in specs)


def _args_brief(args: dict[str, Any], max_chars: int = 80) -> str:
    if not args:
        return ""
    parts: list[str] = []
    for k, v in args.items():
        if isinstance(v, str):
            sval = repr(v if len(v) < 40 else v[:37] + "...")
        elif isinstance(v, list):
            sval = f"<list[{len(v)}]>"
        elif isinstance(v, dict):
            sval = f"<dict[{len(v)}]>"
        else:
            sval = repr(v)
        parts.append(f"{k}={sval}")
    out = ", ".join(parts)
    return out if len(out) <= max_chars else out[:max_chars - 3] + "..."


def _parse_action(text: str) -> tuple[str, dict[str, Any]] | None:
    m = re.search(r"Action:\s*(\w+)", text)
    if m is None:
        return None
    tool_name = m.group(1)
    inp = re.search(r"Action\s*Input:\s*", text[m.end():])
    if inp is None:
        return tool_name, {}
    remainder = text[m.end() + inp.end():].strip()
    if not remainder.startswith("{"):
        return tool_name, {}
    depth, end = 0, 0
    for i, ch in enumerate(remainder):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end == 0:
        return tool_name, {}
    try:
        return tool_name, json.loads(remainder[:end])
    except json.JSONDecodeError:
        return tool_name, {}


class ReActRunner:
    def __init__(
        self,
        session: AnalysisSession,
        tool_names: list[str],
        invoker: "LLMInvoker",
        *,
        agent: str = "react",
        logger: logging.Logger | None = None,
        cfg: ReActConfig | None = None,
    ) -> None:
        self.session = session
        self.specs = get_registry().subset(tool_names)
        self.invoker = invoker
        self.cfg = cfg or ReActConfig()
        self.log = logger or logging.getLogger("evo.harness.react")
        self.agent = agent
        self.stats = ReActStats()

    def run(self, task: str) -> str:
        from evo.agents.memory_curator import MemoryCurator  # noqa: PLC0415  (cycle: curator->react)
        self.stats = ReActStats()
        spec_map = {s.name: s for s in self.specs}
        header = f"## 可用工具\n{_format_tools(self.specs)}\n\n{_REACT_FORMAT}\n\n{task}"
        turns: list[_Turn] = []
        hints: list[str] = []
        working_memory = ""
        curator = MemoryCurator(self.session, agent=self.agent) \
            if self.cfg.use_memory_curator else None
        last_response = ""
        same_streak = 0
        fail_streak = 0
        prev_tool: str | None = None

        for round_idx in range(self.cfg.max_rounds):
            self.session.llm.acquire_slot()
            prompt = self._build_prompt(header, turns, hints, working_memory, round_idx)
            t0 = time.monotonic()
            response = self.invoker.invoke(prompt)
            self.stats.rounds = round_idx + 1
            self.log.info("ReAct round %d (%.2fs, prompt=%d chars, turns=%d)",
                          round_idx + 1, time.monotonic() - t0, len(prompt), len(turns))
            last_response = response

            action = _parse_action(response)
            if action is None:
                violations = self._check_finish(self.stats)
                if violations and self.stats.finish_warnings < self.cfg.max_finish_warnings:
                    self.stats.finish_warnings += 1
                    hints.clear()
                    hints.append(self._format_finish_hint(violations))
                    self.log.info(
                        "Finish blocked (%s); warning %d/%d",
                        ", ".join(violations),
                        self.stats.finish_warnings, self.cfg.max_finish_warnings,
                    )
                    continue
                return response
            tool_name, args = action
            spec = spec_map.get(tool_name)
            t_tool = time.monotonic()
            if spec is None:
                result = ToolResult.failure(
                    tool_name, ErrorCode.INVALID_ARGUMENT,
                    f"Unknown tool: {tool_name}",
                )
            else:
                result = spec.fn(**args) if args else spec.fn()
            ok = result.ok
            summary = spec.summarize_result(result) if spec else f"FAIL unknown tool {tool_name}"

            obs_payload: dict[str, Any] = {"ok": ok, "summary": summary}
            if result.handle:
                obs_payload["handle"] = result.handle
            if not ok and result.error is not None:
                obs_payload["error"] = result.error.message[:300]
            obs = json.dumps(obs_payload, ensure_ascii=False)
            truncated = False

            self.stats.tool_calls[tool_name] = self.stats.tool_calls.get(tool_name, 0) + 1
            self.log.info("Tool %s -> handle=%s ok=%s %s",
                          tool_name, result.handle, ok, summary)
            self.session.telemetry.emit(
                "tool_call", agent=self.agent, tool=tool_name,
                args_keys=sorted(args.keys()), ok=ok, handle=result.handle,
                elapsed_s=round(time.monotonic() - t_tool, 4),
                out_chars=len(obs), truncated=truncated,
            )
            turns.append(_Turn(response=response, tool=tool_name, args=args,
                                obs=obs, ok=ok, summary=summary))
            if curator is not None:
                working_memory = curator.update(
                    working_memory, tool=tool_name,
                    args_brief=_args_brief(args), summary=summary,
                    handle=result.handle, ok=ok,
                )

            same_streak = same_streak + 1 if tool_name == prev_tool else 1
            fail_streak = fail_streak + 1 if not ok else 0
            prev_tool = tool_name
            hints.clear()
            if same_streak >= self.cfg.same_streak_warn:
                self.stats.same_streak_hits += 1
                hints.append(
                    f"提示：你已经连续 {same_streak} 次调用同一个工具 `{tool_name}`，"
                    "再次调用前请改变参数或换一个工具。"
                )
            if fail_streak >= self.cfg.fail_streak_warn:
                self.stats.fail_streak_hits += 1
                hints.append(
                    f"提示：连续 {fail_streak} 次工具失败。请检查 Action 工具名/参数，或换一个工具。"
                )

        self.log.warning("ReAct exhausted %d rounds", self.cfg.max_rounds)
        return last_response

    def _check_finish(self, stats: ReActStats) -> list[str]:
        """Return list of constraint violations (empty = pass)."""
        violations: list[str] = []
        if stats.total_tool_calls < self.cfg.min_tool_calls:
            violations.append(
                f"min_tool_calls={self.cfg.min_tool_calls} (called {stats.total_tool_calls})"
            )
        missing = sorted(set(self.cfg.required_tools) - set(stats.tool_calls.keys()))
        if missing:
            violations.append(f"missing required_tools={missing}")
        return violations

    def _format_finish_hint(self, violations: list[str]) -> str:
        remaining = self.cfg.max_finish_warnings - self.stats.finish_warnings
        return (
            "提示：你试图结束但证据不足 — " + "; ".join(violations) + "。"
            "请继续调用相关工具完善证据；"
            f"再连续坚持结束 {remaining} 次后将允许放行。"
        )

    def _build_prompt(self, header: str, turns: list[_Turn], hints: list[str],
                      working_memory: str, round_idx: int) -> str:
        parts = [header]
        if working_memory:
            parts.append("## 当前已知（自动维护的 working memory）\n" + working_memory)

        keep = 1 if self.cfg.use_memory_curator else self.cfg.window_turns
        n = len(turns)
        if not self.cfg.use_memory_curator and n > keep:
            parts.append("## 历史摘要（参数与摘要）\n" + "\n".join(
                f"  - round {i + 1}: {t.tool}({_args_brief(t.args)}) -> {t.summary}"
                for i, t in enumerate(turns[:n - keep])
            ))
        for t in turns[max(0, n - keep):]:
            parts.append(f"Assistant:\n{t.response}\n\nObservation:\n{t.obs}")

        if hints:
            parts.append("## 系统提示\n" + "\n".join(hints))
        parts.append(self._stage_hint(round_idx))
        return "\n\n".join(parts)

    def _stage_hint(self, round_idx: int) -> str:
        max_r = max(self.cfg.max_rounds, 1)
        progress = round_idx / max_r
        if progress < 0.3:
            return "你下一步打算调用哪个工具来推进调查？请按工作流给出 Thought / Action。"
        if progress < 0.7:
            return "继续基于「当前已知」深入；如仍有未验证的假设，请用相应工具去验证。"
        return "已接近回合上限。如证据已足以支撑结论，直接输出最终 JSON 结果。"


class LLMInvoker:
    def __init__(self, session: AnalysisSession, system_prompt: str,
                 llm: Any | None = None) -> None:
        self.session = session
        self.system_prompt = system_prompt
        self._llm = llm

    def _build_llm(self) -> Any:
        if self._llm is not None:
            return self._llm
        provider = self.session.llm_provider
        if provider is None:
            raise RuntimeError(
                "No llm_provider on session; pass llm_provider=... to "
                "create_session() or RAGAnalysisPipeline."
            )
        llm = provider()
        if llm is None:
            raise RuntimeError("llm_provider returned None.")
        self._llm = llm
        return llm

    @staticmethod
    def _normalize(raw: Any) -> str:
        from evo.utils import strip_thinking
        if isinstance(raw, str):
            return strip_thinking(raw)
        if isinstance(raw, dict):
            c = raw.get("content")
            if isinstance(c, str) and c.strip():
                return strip_thinking(c)
            return json.dumps(raw, ensure_ascii=False)[:50_000]
        return str(raw)

    def invoke(self, user_text: str) -> str:
        llm = self._build_llm()
        try:
            from lazyllm.components import ChatPrompter  # type: ignore
            out = llm.share(prompt=ChatPrompter(instruction=self.system_prompt))(user_text)
        except Exception:
            out = llm(f"{self.system_prompt}\n\n---\n\n{user_text}")
        return self._normalize(out)
