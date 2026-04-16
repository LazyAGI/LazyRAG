"""Base agent with LLM call governance: retry, rate-limit, cache, and ReAct loop."""

from __future__ import annotations

import hashlib
import importlib
import inspect
import json
import logging
import re
import threading
import time
from collections import OrderedDict
from typing import Any, Callable, cast


class _TokenBucket:
    def __init__(self, rate: float = 10.0, burst: int = 15) -> None:
        self._rate, self._burst = rate, burst
        self._tokens, self._last = float(burst), time.monotonic()
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
                raise TimeoutError("Rate limiter timed out")
            time.sleep(0.05)


class _LRUCache:
    def __init__(self, maxsize: int = 128) -> None:
        self._max = maxsize
        self._cache: OrderedDict[str, str] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> str | None:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
        return None

    def put(self, key: str, value: str) -> None:
        with self._lock:
            self._cache[key] = value
            self._cache.move_to_end(key)
            while len(self._cache) > self._max:
                self._cache.popitem(last=False)


_rate_limiter = _TokenBucket()
_response_cache = _LRUCache()

_MAX_RETRIES = 3
_RETRY_BASE = 1.0

_TOOL_IMPORTS: dict[str, tuple[str, str]] = {
    "summarize_metrics":        ("evo.tools.stats",    "summarize_metrics"),
    "correlate_metrics":        ("evo.tools.stats",    "correlate_metrics"),
    "correlate_metrics_enhanced": ("evo.tools.stats",  "correlate_metrics_enhanced"),
    "list_bad_cases":           ("evo.tools.data",     "list_bad_cases"),
    "get_case_detail":          ("evo.tools.data",     "get_case_detail"),
    "compare_cases":            ("evo.tools.data",     "compare_cases"),
    "list_dataset_ids":         ("evo.tools.data",     "list_dataset_ids"),
    "get_session_status":       ("evo.tools.data",     "get_session_status"),
    "list_cases_ranked":        ("evo.tools.evidence", "list_cases_ranked"),
    "export_case_evidence":     ("evo.tools.evidence", "export_case_evidence"),
    "cluster_badcases":         ("evo.tools.cluster",  "cluster_badcases"),
    "get_cluster_summary":      ("evo.tools.cluster",  "get_cluster_summary"),
    "list_cluster_exemplars":   ("evo.tools.cluster",  "list_cluster_exemplars"),
    "cluster_per_step":         ("evo.tools.cluster",  "cluster_per_step"),
    "analyze_step_flow":        ("evo.tools.cluster",  "analyze_step_flow"),
    "get_step_flow_analysis":   ("evo.tools.cluster",  "get_step_flow_analysis"),
    "list_code_map":            ("evo.tools.code",     "list_code_map"),
    "parse_code_structure":     ("evo.tools.code",     "parse_code_structure"),
    "read_source_file":         ("evo.tools.code",     "read_source_file"),
    "extract_config_values":    ("evo.tools.code",     "extract_config_values"),
    "search_code_pattern":      ("evo.tools.code",     "search_code_pattern"),
}

_MAX_REACT_ROUNDS = 10
_MAX_OBSERVATION_CHARS = 40000

_REACT_FORMAT = """\
## 工具调用格式
需要使用工具时，严格使用以下格式（每次只调用一个工具）:

Thought: <你的思考>
Action: <工具名>
Action Input: <JSON 参数>

系统会返回:
Observation: <结果>

当你收集到足够信息后，直接输出最终 JSON 结果（不要再写 Action）。"""


def _cache_key(name: str, q: str) -> str:
    return hashlib.sha256(f"{name}:{q}".encode()).hexdigest()[:24]


class BaseAnalysisAgent:
    """Agent with retry + rate-limit + cache + in-process ReAct loop."""

    _task_heading: str = "初始信息"
    _task_instruction: str = "请按工作流主动使用工具探索数据，完成分析后输出最终结论。"
    _max_case_ids: int = 20
    _perspective_name: str = ""

    def __init__(
        self,
        name: str,
        tool_names: list[str] | None = None,
        llm: Any | None = None,
        logger: logging.Logger | None = None,
        use_cache: bool = True,
        max_retries: int = _MAX_RETRIES,
    ) -> None:
        self.name = name
        self.tool_names = tool_names or []
        self.llm = llm
        self.logger = logger or logging.getLogger(f"evo.agent.{name}")
        self.use_cache = use_cache
        self.max_retries = max_retries
        self._agent: Callable[[str], str] | None = None

    def get_default_system_prompt(self) -> str:
        return "You are a concise technical assistant for RAG diagnostics."

    @staticmethod
    def _normalize(raw: Any) -> str:
        from evo.agents.parsing import _strip_thinking
        if isinstance(raw, str):
            return _strip_thinking(raw)
        if isinstance(raw, dict):
            c = raw.get("content")
            if isinstance(c, str) and c.strip():
                return _strip_thinking(c)
            return json.dumps(raw, ensure_ascii=False)[:50_000]
        return str(raw)

    def analyze(self, briefing_json: str, dataset_ids: list[str]):
        """Shared perspective-agent analysis loop. Subclasses configure via class attrs."""
        from evo.agents.parsing import OUTPUT_SCHEMA, parse_perspective_json
        task = (
            f"## {self._task_heading}\n{briefing_json}\n\n"
            f"## 可调查的 case IDs\n{json.dumps(dataset_ids[:self._max_case_ids])}\n\n"
            f"{self._task_instruction}\n\n"
            f"## 最终输出格式\n{OUTPUT_SCHEMA}"
        )
        raw = self._run_governed_llm(
            lambda: self._run_react_loop(task),
            cache_key=f"{self.name}:{','.join(dataset_ids[:5])}",
            log_preview=self.name,
        )
        return parse_perspective_json(raw, self._perspective_name or self.name, dataset_ids)

    def _invoke_llm_text(self, user_text: str) -> str:
        from chat.pipelines.builders.get_models import get_automodel
        llm = self.llm or get_automodel("evo_llm")
        if llm is None:
            raise ValueError("No LLM available")
        instruction = self.get_default_system_prompt()
        try:
            from lazyllm.components import ChatPrompter
            out = llm.share(prompt=ChatPrompter(instruction=instruction))(user_text)
        except Exception:
            out = llm(f"{instruction}\n\n---\n\n{user_text}")
        return self._normalize(out)

    def _run_governed_llm(self, producer: Callable[[], str], cache_key: str, log_preview: str) -> str:
        if self.use_cache:
            cached = _response_cache.get(_cache_key(self.name, cache_key))
            if cached is not None:
                return cached
        last_err: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                _rate_limiter.acquire()
                t0 = time.monotonic()
                result = producer()
                self.logger.info("Agent %s done (attempt=%d, %.2fs)", self.name, attempt, time.monotonic() - t0)
                if self.use_cache:
                    _response_cache.put(_cache_key(self.name, cache_key), result)
                return result
            except Exception as e:
                last_err = e
                if attempt < self.max_retries:
                    time.sleep(_RETRY_BASE * 2 ** (attempt - 1))
                    self.logger.warning("Agent %s attempt %d failed: %s", self.name, attempt, e)
        raise cast(Exception, last_err)

    # ------------------------------------------------------------------
    # In-process ReAct loop (avoids lazyllm sandbox + thinking-mode bugs)
    # ------------------------------------------------------------------

    def _resolve_tools(self) -> dict[str, Callable[..., str]]:
        """Import tool functions in-process by name."""
        tools: dict[str, Callable[..., str]] = {}
        for name in self.tool_names:
            entry = _TOOL_IMPORTS.get(name)
            if entry is None:
                self.logger.warning("Unknown tool: %s", name)
                continue
            mod_path, func_name = entry
            mod = importlib.import_module(mod_path)
            tools[name] = getattr(mod, func_name)
        return tools

    @staticmethod
    def _format_tool_descs(tools: dict[str, Callable[..., str]]) -> str:
        parts: list[str] = []
        for name, fn in tools.items():
            sig = inspect.signature(fn)
            params = []
            for pname, param in sig.parameters.items():
                p = pname
                if param.default is not inspect.Parameter.empty:
                    p += f"={param.default!r}"
                params.append(p)
            doc = (fn.__doc__ or "").strip().split("\n\n")[0]
            parts.append(f"- **{name}**({', '.join(params)}): {doc}")
        return "\n".join(parts)

    @staticmethod
    def _parse_action(text: str) -> tuple[str, dict[str, Any]] | None:
        """Extract first Action / Action Input from LLM response."""
        m = re.search(r'Action:\s*(\w+)', text)
        if m is None:
            return None
        tool_name = m.group(1)
        inp = re.search(r'Action\s*Input:\s*', text[m.end():])
        if inp is None:
            return (tool_name, {})
        json_start = m.end() + inp.end()
        remainder = text[json_start:].strip()
        if not remainder.startswith("{"):
            return (tool_name, {})
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
            return (tool_name, {})
        try:
            args = json.loads(remainder[:end])
        except json.JSONDecodeError:
            return (tool_name, {})
        return (tool_name, args)

    def _run_react_loop(self, task: str, max_rounds: int = _MAX_REACT_ROUNDS) -> str:
        """Text-based ReAct loop. Tools execute in-process (no sandbox)."""
        tools = self._resolve_tools()
        tool_descs = self._format_tool_descs(tools)
        history = f"## 可用工具\n{tool_descs}\n\n{_REACT_FORMAT}\n\n{task}"
        last_response = ""

        for round_idx in range(max_rounds):
            _rate_limiter.acquire()
            t0 = time.monotonic()
            response = self._invoke_llm_text(history)
            elapsed = time.monotonic() - t0
            self.logger.info("Agent %s round %d (%.2fs, history=%d chars)",
                             self.name, round_idx + 1, elapsed, len(history))
            last_response = response

            action = self._parse_action(response)
            if action is None:
                self.logger.info("Agent %s finished after %d rounds", self.name, round_idx + 1)
                return response

            tool_name, args = action
            tool_fn = tools.get(tool_name)
            if tool_fn is None:
                result = json.dumps({"ok": False, "error": f"Unknown tool: {tool_name}"})
            else:
                try:
                    if args:
                        result = tool_fn(**args)
                    else:
                        result = tool_fn()
                except Exception as e:
                    result = json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"})

            if len(result) > _MAX_OBSERVATION_CHARS:
                result = result[:_MAX_OBSERVATION_CHARS] + "\n... [TRUNCATED]"

            self.logger.info("Agent %s called %s -> %d chars", self.name, tool_name, len(result))
            history += (
                f"\n\nAssistant:\n{response}\n\n"
                f"Observation:\n{result}\n\n"
                "请基于以上结果继续分析。如果信息已充分，直接输出最终 JSON 结果。"
            )

        self.logger.warning("Agent %s exhausted %d rounds", self.name, max_rounds)
        return last_response

    # ------------------------------------------------------------------
    # Legacy: ReactAgent-based (kept for interactive mode)
    # ------------------------------------------------------------------

    def build_agent(self) -> Callable[[str], str]:
        if self._agent is not None:
            return self._agent
        from chat.pipelines.builders.get_models import get_automodel
        self.llm = self.llm or get_automodel("evo_llm")
        if self.llm is None:
            raise ValueError("No LLM available")
        if not self.tool_names:
            self._agent = self._invoke_llm_text
            return self._agent
        from lazyllm.tools import ReactAgent
        self._agent = ReactAgent(self.llm, self.tool_names)
        return cast(Callable[[str], str], self._agent)

    def analyze(self, query: str) -> str:
        self.build_agent()
        return self._run_governed_llm(
            lambda: cast(Callable[[str], str], self._agent)(query),
            cache_key=query, log_preview=query,
        )
