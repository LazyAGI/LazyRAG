from __future__ import annotations
import json
import inspect
import logging
import re
import time
from dataclasses import asdict, dataclass, is_dataclass
from typing import Any
from evo.domain.tool_result import ToolResult
from evo.harness.registry import ToolSpec, get_registry
from evo.runtime.session import AnalysisSession

_REACT_FORMAT = (
    '## 工具调用格式\n'
    '需要使用工具时，严格使用以下格式（每次只调用一个工具）:\n\n'
    'Thought: <你的思考>\n'
    'Action: <工具名>\n'
    'Action Input: <JSON 参数>\n\n'
    '系统会返回:\n'
    'Observation: <结果>\n\n'
    '收集到足够证据后，直接输出最终 JSON 结果（不要再写 Action）。'
)


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
    tool_calls: dict[str, int] = None
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
    summary: str


def _format_tools(specs: list[ToolSpec]) -> str:
    return '\n'.join((spec.describe() for spec in specs))


def _runtime_context(session: AnalysisSession) -> str:
    global_clusters = [
        cs.cluster_id for cs in (session.clustering_global.cluster_summaries if session.clustering_global else [])
    ]
    per_step_clusters = {
        step: [cs.cluster_id for cs in result.cluster_summaries]
        for (step, result) in (session.clustering_per_step.per_step.items() if session.clustering_per_step else [])
    }
    score_fields = _numeric_judge_fields(session)
    payload = {
        'global_cluster_ids': global_clusters,
        'per_step_cluster_ids': per_step_clusters,
        'step_keys': list(session.trace_meta.pipeline),
        'score_fields': score_fields,
        'sample_dataset_ids': session.sample_dataset_ids(8),
    }
    return (
        f'## 当前运行的工具参数边界（强约束）\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n'
        '- cluster_id 必须逐字来自 global_cluster_ids 或对应 step 的 per_step_cluster_ids；'
        '禁止使用占位符、空值或自行编造。\n'
        '- step_key 必须逐字来自 step_keys；score_field 必须逐字来自 score_fields。\n'
        '- limit/k/offset 必须是整数，threshold 必须是数字。\n'
        '- dataset_id 必须来自 sample_dataset_ids，或来自你实际调用过的 '
        'list_bad_cases / list_cases_ranked / list_cluster_exemplars 返回值。'
    )


def _numeric_judge_fields(session: AnalysisSession) -> list[str]:
    fields: set[str] = set()
    for _did, judge in list(session.iter_judge())[:5]:
        data = asdict(judge) if is_dataclass(judge) else vars(judge)
        for key, value in data.items():
            if isinstance(value, (int, float)) and (not isinstance(value, bool)):
                fields.add(key)
    return sorted(fields)


def _args_brief(args: dict[str, Any], max_chars: int = 80) -> str:
    if not args:
        return ''
    parts: list[str] = []
    for k, v in args.items():
        if isinstance(v, str):
            sval = repr(v if len(v) < 40 else v[:37] + '...')
        elif isinstance(v, list):
            sval = f'<list[{len(v)}]>'
        elif isinstance(v, dict):
            sval = f'<dict[{len(v)}]>'
        else:
            sval = repr(v)
        parts.append(f'{k}={sval}')
    out = ', '.join(parts)
    return out if len(out) <= max_chars else out[: max_chars - 3] + '...'


_FORMAT_VIOLATION_RES: tuple[re.Pattern, ...] = (
    re.compile('\\[TOOL_CALL\\]'),
    re.compile('<invoke\\b'),
    re.compile('<\\w+:tool_call\\b'),
    re.compile('"\\s*(?:tool|name|function|tool_name)\\s*"\\s*:\\s*"'),
    re.compile('```tool_code'),
)


def _parse_action(text: str) -> tuple[str, dict[str, Any]] | None:
    m = re.search('Action:\\s*(\\w+)', text)
    if m is not None:
        tool_name = m.group(1)
        inp = re.search('Action\\s*Input:\\s*', text[m.end():])
        if inp is None:
            return (tool_name, {})
        args = _parse_json_object(text[m.end() + inp.end():].strip())
        return (tool_name, args or {})
    invoke = re.search('<invoke\\s+name=["\\\'](?P<name>\\w+)["\\\']\\s*>', text)
    if invoke is not None:
        args: dict[str, Any] = {}
        body = text[invoke.end():]
        for name, value in re.findall(
            '<parameter\\s+name=["\\\'](\\w+)["\\\']\\s*>(.*?)</parameter>', body, flags=re.DOTALL
        ):
            args[name] = value.strip()
        return (invoke.group('name'), args)
    mm = re.search('<minimax:tool_call\\b[^>]*>(.*?)(?:</minimax:tool_call>|$)', text, flags=re.DOTALL)
    if mm is not None:
        body = mm.group(1).strip()
        inline = re.search('invoke\\s+(?:name=)?["\\\']?(?P<name>\\w+)["\\\']?', body)
        if inline is not None:
            return (inline.group('name'), _parse_minimax_args(body))
        tag = re.search('<(?P<name>\\w+)>\\s*(?P<body>.*)', body, re.DOTALL)
        if tag is not None:
            return (tag.group('name'), _parse_minimax_args(tag.group('body')))
        lines = [line.strip() for line in body.splitlines() if line.strip()]
        if lines:
            name = lines[0]
            if re.fullmatch('\\w+', name):
                return (name, _parse_minimax_args(body))
    return None


def _parse_minimax_args(text: str) -> dict[str, Any]:
    obj = _parse_json_object(text)
    if obj is not None:
        return obj
    out: dict[str, Any] = {}
    for key, value in re.findall('<(?P<key>\\w+):\\s*(?P<value>[^<>\\n]+)(?:</\\w+>)?>', text):
        out[key] = value.strip()
    return out


def _parse_json_object(text: str) -> dict[str, Any] | None:
    start = text.find('{')
    if start < 0:
        return None
    fragment = text[start:]
    depth, end = (0, 0)
    for i, ch in enumerate(fragment):
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end == 0:
        return None
    try:
        obj = json.loads(fragment[:end])
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _normalize_args(spec: ToolSpec, args: dict[str, Any]) -> dict[str, Any]:
    if spec.name == 'read_source_file' and 'file' in args and ('file_path' not in args):
        args = {**args, 'file_path': args['file']}
    if spec.name == 'list_cluster_exemplars' and 'limit' in args and ('k' not in args):
        args = {**args, 'k': args['limit']}
    out: dict[str, Any] = {}
    for name, value in args.items():
        if name in {'file', 'limit'} and spec.name in {'read_source_file', 'list_cluster_exemplars'}:
            continue
        param = spec.signature.parameters.get(name)
        if param is None:
            continue
        out[name] = _coerce_value(value, param.annotation, param.default)
    return out


def _coerce_value(value: Any, annotation: Any, default: Any) -> Any:
    target = annotation if annotation is not inspect.Parameter.empty else type(default)
    if target in (int, 'int') and isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default if default is not inspect.Parameter.empty else value
    if target in (float, 'float') and isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default if default is not inspect.Parameter.empty else value
    return value


def _looks_like_pseudo_tool_call(text: str) -> bool:
    return any((p.search(text) for p in _FORMAT_VIOLATION_RES))


def _tool_result_payload(result: ToolResult) -> dict[str, Any]:
    try:
        return result.as_dict()
    except Exception as exc:
        return {'ok': result.ok, 'error': f'failed to serialize result: {exc}'}


class ReActRunner:
    def __init__(
        self,
        session: AnalysisSession,
        tool_names: list[str],
        invoker: 'LLMInvoker',
        *,
        agent: str = 'react',
        logger: logging.Logger | None = None,
        cfg: ReActConfig | None = None,
    ) -> None:
        self.session = session
        self.specs = get_registry().subset(tool_names)
        self.invoker = invoker
        self.cfg = cfg or ReActConfig()
        self.log = logger or logging.getLogger('evo.harness.react')
        self.agent = agent
        self.stats = ReActStats()

    def run(self, task: str) -> str:
        from evo.agents.memory_curator import MemoryCurator

        self.stats = ReActStats()
        spec_map = {s.name: s for s in self.specs}
        runtime_ctx = _runtime_context(self.session)
        header = f'## 可用工具\n{_format_tools(self.specs)}\n\n{runtime_ctx}\n\n{_REACT_FORMAT}\n\n{task}'
        turns: list[_Turn] = []
        hints: list[str] = []
        working_memory = ''
        curator = MemoryCurator(self.session, agent=self.agent) if self.cfg.use_memory_curator else None
        last_response = ''
        same_streak = 0
        fail_streak = 0
        prev_tool: str | None = None
        self.session.telemetry.emit(
            'researcher.started', actor=self.agent, task=task, tools=[s.name for s in self.specs]
        )
        for round_idx in range(self.cfg.max_rounds):
            self.session.llm.acquire_slot()
            prompt = self._build_prompt(header, turns, hints, working_memory, round_idx)
            t0 = time.monotonic()
            response = self.invoker.invoke(prompt)
            self.session.telemetry.emit(
                'researcher.turn.completed',
                actor=self.agent,
                round=round_idx + 1,
                prompt=prompt,
                response=response,
                elapsed_s=round(time.monotonic() - t0, 4),
            )
            self.stats.rounds = round_idx + 1
            self.log.info(
                'ReAct round %d (%.2fs, prompt=%d chars, turns=%d)',
                round_idx + 1,
                time.monotonic() - t0,
                len(prompt),
                len(turns),
            )
            last_response = response
            action = _parse_action(response)
            if action is None:
                violations = list(self._check_finish(self.stats))
                if _looks_like_pseudo_tool_call(response):
                    violations.append('non-standard tool-call syntax')
                if violations and self.stats.finish_warnings < self.cfg.max_finish_warnings:
                    self.stats.finish_warnings += 1
                    hints.clear()
                    hints.append(self._format_finish_hint(violations))
                    self.log.info(
                        'Finish blocked (%s); warning %d/%d',
                        ', '.join(violations),
                        self.stats.finish_warnings,
                        self.cfg.max_finish_warnings,
                    )
                    continue
                self.session.telemetry.emit(
                    'researcher.reasoning_summary',
                    actor=self.agent,
                    rounds=self.stats.rounds,
                    tool_calls=dict(self.stats.tool_calls),
                    final_answer=response,
                )
                return response
            tool_name, args = action
            spec = spec_map.get(tool_name)
            t_tool = time.monotonic()
            if spec is None:
                self.session.telemetry.emit(
                    'researcher.tool_call.failed',
                    actor=self.agent,
                    round=round_idx + 1,
                    tool=tool_name,
                    args=args,
                    error='unknown tool',
                )
                hints.clear()
                hints.append(f'工具 `{tool_name}` 不在可用工具列表中。只能从这些工具中选择：{sorted(spec_map)}')
                continue
            else:
                args = _normalize_args(spec, args)
                self.session.telemetry.emit(
                    'researcher.tool_call.started', actor=self.agent, round=round_idx + 1, tool=tool_name, args=args
                )
                result = spec.fn(**args) if args else spec.fn()
            ok = result.ok
            summary = spec.summarize_result(result) if spec else f'FAIL unknown tool {tool_name}'
            self.session.telemetry.emit(
                'researcher.tool_call.completed',
                actor=self.agent,
                round=round_idx + 1,
                tool=tool_name,
                args=args,
                ok=ok,
                handle=result.handle,
                output=_tool_result_payload(result),
                summary=summary,
                elapsed_s=round(time.monotonic() - t_tool, 4),
            )
            if not ok:
                hints.clear()
                hints.append(
                    f'工具 `{tool_name}` 参数无效或未命中：{summary}。'
                    '请检查上一条 Observation 中的真实 handle/dataset_id/cluster_id，'
                    '或换用 list_bad_cases / list_cases_ranked / list_cluster_exemplars 获取真实 ID。'
                )
                turns.append(
                    _Turn(
                        response=response,
                        tool=tool_name,
                        args=args,
                        obs=json.dumps({'ok': False, 'summary': summary}, ensure_ascii=False),
                        ok=False,
                        summary=summary,
                    )
                )
                continue
            obs_payload: dict[str, Any] = {'ok': ok, 'summary': summary}
            if result.handle:
                obs_payload['handle'] = result.handle
            if not ok and result.error is not None:
                obs_payload['error'] = result.error.message[:300]
            obs = json.dumps(obs_payload, ensure_ascii=False)
            self.session.telemetry.emit(
                'researcher.observation', actor=self.agent, round=round_idx + 1, tool=tool_name, observation=obs_payload
            )
            truncated = False
            self.stats.tool_calls[tool_name] = self.stats.tool_calls.get(tool_name, 0) + 1
            self.log.info('Tool %s -> handle=%s ok=%s %s', tool_name, result.handle, ok, summary)
            self.session.telemetry.emit(
                'tool_call',
                agent=self.agent,
                tool=tool_name,
                args_keys=sorted(args.keys()),
                ok=ok,
                handle=result.handle,
                elapsed_s=round(time.monotonic() - t_tool, 4),
                out_chars=len(obs),
                truncated=truncated,
            )
            turns.append(_Turn(response=response, tool=tool_name, args=args, obs=obs, ok=ok, summary=summary))
            if curator is not None:
                working_memory = curator.update(
                    working_memory,
                    tool=tool_name,
                    args_brief=_args_brief(args),
                    summary=summary,
                    handle=result.handle,
                    ok=ok,
                )
            same_streak = same_streak + 1 if tool_name == prev_tool else 1
            fail_streak = fail_streak + 1 if not ok else 0
            prev_tool = tool_name
            hints.clear()
            if same_streak >= self.cfg.same_streak_warn:
                self.stats.same_streak_hits += 1
                hints.append(
                    f'提示：你已经连续 {same_streak} 次调用同一个工具 `{tool_name}`，再次调用前请改变参数或换一个工具。'
                )
            if fail_streak >= self.cfg.fail_streak_warn:
                self.stats.fail_streak_hits += 1
                hints.append(f'提示：连续 {fail_streak} 次工具失败。请检查 Action 工具名/参数，或换一个工具。')
        self.log.warning('ReAct exhausted %d rounds', self.cfg.max_rounds)
        self.session.telemetry.emit(
            'researcher.reasoning_summary',
            actor=self.agent,
            rounds=self.stats.rounds,
            tool_calls=dict(self.stats.tool_calls),
            final_answer=last_response,
            exhausted=True,
        )
        return last_response

    def _check_finish(self, stats: ReActStats) -> list[str]:
        violations: list[str] = []
        if stats.total_tool_calls < self.cfg.min_tool_calls:
            violations.append(f'min_tool_calls={self.cfg.min_tool_calls} (called {stats.total_tool_calls})')
        missing = sorted(set(self.cfg.required_tools) - set(stats.tool_calls.keys()))
        if missing:
            violations.append(f'missing required_tools={missing}')
        return violations

    def _format_finish_hint(self, violations: list[str]) -> str:
        remaining = self.cfg.max_finish_warnings - self.stats.finish_warnings
        parts = ['提示：本轮输出无法被解析 — ' + '; '.join(violations) + '。']
        if any(('non-standard' in v for v in violations)):
            parts.append(
                '本系统【唯一】支持的工具调用格式是：\n'
                'Thought: <thought>\n'
                'Action: <tool_name>\n'
                'Action Input: {<json>}\n'
                '请勿使用 [TOOL_CALL]{...} / <invoke> / <tool_call> 等其它格式；'
                '若已收集到足够证据则直接输出最终 JSON 结果（不要再写 Action）。'
            )
        else:
            parts.append('请继续调用相关工具完善证据；')
        parts.append(f'再连续 {remaining} 次违规将允许放行。')
        return ' '.join(parts)

    def _build_prompt(
        self, header: str, turns: list[_Turn], hints: list[str], working_memory: str, round_idx: int
    ) -> str:
        parts = [header]
        if working_memory:
            parts.append('## 当前已知（自动维护的 working memory）\n' + working_memory)
        keep = 1 if self.cfg.use_memory_curator else self.cfg.window_turns
        n = len(turns)
        if not self.cfg.use_memory_curator and n > keep:
            parts.append(
                '## 历史摘要（参数与摘要）\n'
                + '\n'.join(
                    (
                        f'  - round {i + 1}: {t.tool}({_args_brief(t.args)}) -> {t.summary}'
                        for (i, t) in enumerate(turns[: n - keep])
                    )
                )
            )
        for t in turns[max(0, n - keep):]:
            parts.append(f'Assistant:\n{t.response}\n\nObservation:\n{t.obs}')
        if hints:
            parts.append('## 系统提示\n' + '\n'.join(hints))
        parts.append(self._stage_hint(round_idx))
        return '\n\n'.join(parts)

    def _stage_hint(self, round_idx: int) -> str:
        max_r = max(self.cfg.max_rounds, 1)
        progress = round_idx / max_r
        if progress < 0.3:
            return '你下一步打算调用哪个工具来推进调查？请按工作流给出 Thought / Action。'
        if progress < 0.7:
            return '继续基于「当前已知」深入；如仍有未验证的假设，请用相应工具去验证。'
        return '已接近回合上限。如证据已足以支撑结论，直接输出最终 JSON 结果。'


class LLMInvoker:
    def __init__(self, session: AnalysisSession, system_prompt: str, llm: Any | None = None) -> None:
        self.session = session
        self.system_prompt = system_prompt
        self._llm = llm

    def _build_llm(self) -> Any:
        if self._llm is not None:
            return self._llm
        provider = self.session.llm_provider
        if provider is None:
            raise RuntimeError(
                'No llm_provider on session; pass llm_provider=... to create_session() or RAGAnalysisPipeline.'
            )
        llm = provider()
        if llm is None:
            raise RuntimeError('llm_provider returned None.')
        self._llm = llm
        return llm

    @staticmethod
    def _normalize(raw: Any) -> str:
        from evo.utils import strip_thinking

        if isinstance(raw, str):
            return strip_thinking(raw)
        if isinstance(raw, dict):
            c = raw.get('content')
            if isinstance(c, str) and c.strip():
                return strip_thinking(c)
            return json.dumps(raw, ensure_ascii=False)[:50000]
        return str(raw)

    def invoke(self, user_text: str, *, system_prompt: str | None = None) -> str:
        llm = self._build_llm()
        sp = self.system_prompt if system_prompt is None else system_prompt
        full_prompt = f'{sp}\n\n---\n\n{user_text}'
        self.session.telemetry.emit(
            'llm.prompt', actor='llm', system_prompt=sp, user_text=user_text, full_prompt=full_prompt
        )
        t0 = time.monotonic()
        try:
            from lazyllm.components import ChatPrompter

            out = llm.share(prompt=ChatPrompter(instruction=sp))(user_text)
        except Exception:
            out = llm(full_prompt)
        normalized = self._normalize(out)
        self.session.telemetry.emit(
            'llm.answer', actor='llm', answer=normalized, raw=out, elapsed_s=round(time.monotonic() - t0, 4)
        )
        return normalized
