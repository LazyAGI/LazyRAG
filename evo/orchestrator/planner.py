from __future__ import annotations
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator
from evo.orchestrator import capabilities as caps
from evo.service.core import schemas
from evo.service.core.intent_store import Intent, IntentPreview, PlanResult


@dataclass
class PlanContext:
    thread_id: str
    recent_history: list[tuple[str, str]] = field(default_factory=list)
    thread_state_summary: str = ''
    capabilities_with_safety: list[dict] = field(default_factory=list)
    thread_state: dict[str, Any] = field(default_factory=dict)


class Planner:
    def __init__(
        self,
        *,
        llm: Callable[[str], Any],
        stream_llm: Callable[[str, Callable[[], bool]], Iterator[str]] | None = None,
    ) -> None:
        self.llm = llm
        self.stream_llm = stream_llm

    def draft(self, message: str, ctx: PlanContext) -> Intent:
        import uuid

        cap_summary = '\n'.join(
            (f"- {c['op']} (flow={c['flow']}, safety={c['safety']})" for c in ctx.capabilities_with_safety)
        )
        artifact_hint = ''
        prompt = ''
        raw_answer: Any = None
        source = 'heuristic'
        if (ctx.thread_state or {}).get('pending_checkpoint'):
            source = 'checkpoint_llm'
            parsed, prompt, raw_answer = _checkpoint_plan(message, ctx, self.llm)
        else:
            if ctx.thread_state_summary:
                artifact_hint = (
                    f'\n\nCurrent thread artifacts:\n{ctx.thread_state_summary}\n\n'
                    "When user refers to '刚才的/最新的/上一个', use these artifact IDs."
                )
            parsed = _heuristic_plan(message, ctx)
            if parsed is None:
                source = 'llm'
                prompt = (
                    f'User message: {message}{artifact_hint}\n\n'
                    f'Available operations:\n{cap_summary}\n\n'
                    "You are a task planner. Map the user's natural language request to operations.\n"
                    'Rules:\n'
                    '- For interruption/retry/re-run requests, prefer task.stop_active/task.continue_latest '
                    'plus the restart op.\n'
                    '- If user says a dataset is bad and asks to regenerate while analysis is running, '
                    'emit task.stop_active(flow=run) before dataset_gen.start.\n'
                    "- '创建评测集/生成数据集' -> dataset_gen.start with kb_id, eval_name\n"
                    "- '评测/跑评测/生成报告' -> eval.run with dataset_id, target_chat_url; "
                    'if user mentions dataset_name/数据集名/alias, put it in args.options.dataset_name\n'
                    "- '分析/诊断' -> run.start with eval_id\n"
                    "- '修改代码/apply' -> apply.start with report_id. apply already loops code edits "
                    'and unit tests; do not emit multiple apply.start for one report.\n'
                    "- 'ABTest/对比' -> abtest.create with apply_id, baseline_eval_id, dataset_id only "
                    'after the apply is succeeded/accepted and its final unit-test round passed.\n'
                    '- Extract specific IDs from artifacts when user refers to them\n'
                    'Reply in strict JSON only: '
                    '{"reply":"...","ops":[{"op":"...","reason":"...","args":{...}}]}'
                )
                try:
                    raw_answer = self.llm(prompt)
                    parsed = _parse_json_object(raw_answer)
                    if not isinstance(parsed, dict):
                        raise ValueError('planner response must be an object')
                except Exception:
                    parsed = {'ops': [], 'reply': f'收到：{message}。暂无可自动执行的操作。'}
            else:
                raw_answer = parsed
        return self._intent_from_parsed(message, ctx, parsed, source=source, prompt=prompt, raw_answer=raw_answer)

    def draft_stream(
        self, message: str, ctx: PlanContext, cancel_requested: Callable[[], bool]
    ) -> Iterator[dict[str, Any]]:
        if self.stream_llm is None:
            yield {'type': 'final', 'intent': self.draft(message, ctx)}
            return
        source = 'heuristic'
        prompt = ''
        raw_answer: Any = None
        if (ctx.thread_state or {}).get('pending_checkpoint'):
            checkpoint = (ctx.thread_state or {}).get('pending_checkpoint') or {}
            auto_plan = _checkpoint_autooperator_plan(message, checkpoint)
            if auto_plan is not None:
                op = (auto_plan.get('ops') or [{}])[0]
                _validate_checkpoint_boundary(str(op.get('op')), op.get('args') or {}, ctx)
                intent = self._intent_from_parsed(
                    message, ctx, auto_plan, source='checkpoint_heuristic', prompt='', raw_answer=auto_plan
                )
                if intent.reply:
                    yield {'type': 'reply_delta', 'delta': intent.reply}
                yield {'type': 'final', 'intent': intent}
                return
            source = 'checkpoint_llm'
            prompt = _checkpoint_prompt(message, ctx)
            parsed, raw_answer, emitted_reply = yield from self._stream_json_plan(prompt, cancel_requested)
            try:
                ops = parsed.get('ops') or []
                if len(ops) != 1:
                    raise ValueError('checkpoint mode requires exactly one command')
                op = ops[0].get('op')
                args = ops[0].get('args') or {}
                if op == 'checkpoint.answer' and not args.get('message'):
                    args['message'] = parsed.get('reply') or '我会保留当前断点，先回答你的问题。'
                    ops[0]['args'] = args
                model_by_op = {
                    'checkpoint.continue': schemas.CheckpointContinue,
                    'checkpoint.rewind': schemas.CheckpointRewind,
                    'checkpoint.answer': schemas.CheckpointAnswer,
                    'checkpoint.cancel': schemas.CheckpointCancel,
                }
                if op not in model_by_op:
                    raise ValueError(f'unsupported checkpoint command {op!r}')
                model_by_op[op](**args)
                _validate_checkpoint_boundary(op, args, ctx)
            except Exception as exc:
                parsed = {
                    'ops': [
                        {
                            'op': 'checkpoint.answer',
                            'reason': '无法将用户消息校验为可执行断点命令',
                            'args': {'message': f'我还在等待当前断点确认，但无法安全执行这条消息：{exc}'},
                        }
                    ],
                    'reply': f'我还在等待当前断点确认，但无法安全执行这条消息：{exc}',
                }
                raw_answer = parsed
        else:
            parsed = _heuristic_plan(message, ctx)
            if parsed is None:
                source = 'llm'
                prompt = _planner_prompt(message, ctx)
                parsed, raw_answer, emitted_reply = yield from self._stream_json_plan(prompt, cancel_requested)
            else:
                raw_answer = parsed
                emitted_reply = ''
        intent = self._intent_from_parsed(message, ctx, parsed, source=source, prompt=prompt, raw_answer=raw_answer)
        suffix = intent.reply
        if emitted_reply and suffix.startswith(emitted_reply):
            suffix = suffix[len(emitted_reply):]
        if suffix:
            yield {'type': 'reply_delta', 'delta': suffix}
        yield {'type': 'final', 'intent': intent}

    def _stream_json_plan(
        self, prompt: str, cancel_requested: Callable[[], bool]
    ) -> Iterator[dict[str, Any]]:
        raw_parts: list[str] = []
        reply = _ReplyDeltaExtractor()
        for chunk in self.stream_llm(prompt, cancel_requested) if self.stream_llm else ():
            if cancel_requested():
                raise RuntimeError('MESSAGE_CANCELLED')
            text = str(chunk or '')
            if not text:
                continue
            raw_parts.append(text)
            delta = reply.feed(text)
            if delta:
                yield {'type': 'reply_delta', 'delta': delta}
        raw = ''.join(raw_parts)
        return _parse_json_object(raw), raw, reply.text

    def _intent_from_parsed(
        self, message: str, ctx: PlanContext, parsed: dict[str, Any], *, source: str, prompt: str, raw_answer: Any
    ) -> Intent:
        import uuid

        selected_ops = parsed.get('ops', [])
        previews: list[IntentPreview] = []
        warnings: list[str] = []
        for sel in selected_ops:
            op_name = sel.get('op', '')
            if not op_name or op_name not in caps.REGISTRY:
                warnings.append(f'unknown op: {op_name}')
                continue
            cap = caps.get(op_name)
            previews.append(
                IntentPreview(
                    op=op_name,
                    humanized=sel.get('reason', f'{cap.flow}: {cap.description}'),
                    safety=cap.safety,
                    params_summary=sel.get('args', {}),
                )
            )
        requires_confirm = False
        reply = parsed.get('reply', f'收到：{message}。')
        if previews and previews[0].op not in {'checkpoint.answer', 'checkpoint.cancel'}:
            reply += ' 我会在后台执行，并把过程写入事件流。'
        return Intent(
            intent_id=f'intent_{ctx.thread_id}_{uuid.uuid4().hex[:8]}',
            thread_id=ctx.thread_id,
            user_message=message,
            reply=reply,
            suggested_ops_preview=previews,
            requires_confirm=requires_confirm,
            thinking=parsed.get('thinking', ''),
            trace={
                'source': source,
                'prompt': prompt,
                'raw_answer': raw_answer,
                'parsed': parsed,
                'warnings': warnings,
            },
        )

    def materialize(self, intent: Intent, ctx: PlanContext, user_edit: dict | None = None) -> PlanResult:
        ops: list[dict[str, Any]] = []
        warnings: list[str] = []
        raw_ops = user_edit.get('ops', []) if user_edit else None
        if raw_ops is None:
            raw_ops = [{'op': preview.op, 'args': preview.params_summary} for preview in intent.suggested_ops_preview]
        validation_details: list[dict[str, Any]] = []
        for op_data in raw_ops:
            try:
                op_name = op_data['op']
                args = op_data.get('args', {})
                caps.validate(op_name, args)
                _validate_schema(op_name, args, ctx)
                ops.append({'op': op_name, 'args': args})
                validation_details.append({'op': op_name, 'args': args, 'status': 'accepted'})
            except (KeyError, TypeError, ValueError) as exc:
                warnings.append(f'validation failed: {exc}')
                validation_details.append(
                    {
                        'op': op_data.get('op') if isinstance(op_data, dict) else None,
                        'args': op_data.get('args') if isinstance(op_data, dict) else None,
                        'status': 'rejected',
                        'error': str(exc),
                    }
                )
        return PlanResult(
            intent_id=intent.intent_id,
            ops=ops,
            warnings=warnings,
            trace={'raw_ops': raw_ops, 'validation': validation_details},
        )


def _validate_schema(op: str, args: dict[str, Any], ctx: PlanContext) -> None:
    model_by_op = {
        'run.start': schemas.RunCreate,
        'apply.start': schemas.ApplyCreate,
        'dataset_gen.start': schemas.DatasetGenCreate,
        'eval.run': schemas.EvalCreate,
        'eval.fetch': schemas.EvalCreate,
        'abtest.create': schemas.AbtestCreate,
        'checkpoint.continue': schemas.CheckpointContinue,
        'checkpoint.rewind': schemas.CheckpointRewind,
        'checkpoint.answer': schemas.CheckpointAnswer,
        'checkpoint.cancel': schemas.CheckpointCancel,
    }
    model = model_by_op.get(op)
    if model is None:
        return
    payload = dict(args)
    if 'thread_id' not in payload:
        payload['thread_id'] = ctx.thread_id
    model(**payload)
    if op == 'abtest.create':
        _validate_abtest_boundary(payload, ctx)
    if op.startswith('checkpoint.'):
        _validate_checkpoint_boundary(op, payload, ctx)


def _checkpoint_plan(message: str, ctx: PlanContext, llm: Callable[[str], Any]) -> tuple[dict[str, Any], str, Any]:
    checkpoint = (ctx.thread_state or {}).get('pending_checkpoint') or {}
    auto_plan = _checkpoint_autooperator_plan(message, checkpoint)
    if auto_plan is not None:
        op = (auto_plan.get('ops') or [{}])[0]
        _validate_checkpoint_boundary(str(op.get('op')), op.get('args') or {}, ctx)
        return (auto_plan, '', auto_plan)
    last_error = ''
    raw: Any = None
    prompt = ''
    for _ in range(2):
        prompt = _checkpoint_prompt(message, ctx, last_error=last_error)
        try:
            raw = llm(prompt)
            parsed = _parse_json_object(raw)
            ops = parsed.get('ops') or []
            if len(ops) != 1:
                raise ValueError('checkpoint mode requires exactly one command')
            op = ops[0].get('op')
            args = ops[0].get('args') or {}
            if op == 'checkpoint.answer' and not args.get('message'):
                args['message'] = parsed.get('reply') or '我会保留当前断点，先回答你的问题。'
                ops[0]['args'] = args
            model_by_op = {
                'checkpoint.continue': schemas.CheckpointContinue,
                'checkpoint.rewind': schemas.CheckpointRewind,
                'checkpoint.answer': schemas.CheckpointAnswer,
                'checkpoint.cancel': schemas.CheckpointCancel,
            }
            if op not in model_by_op:
                raise ValueError(f'unsupported checkpoint command {op!r}')
            model_by_op[op](**args)
            _validate_checkpoint_boundary(op, args, ctx)
            return (parsed, prompt, raw)
        except Exception as exc:
            last_error = str(exc)
    return (
        {
            'ops': [
                {
                    'op': 'checkpoint.answer',
                    'reason': '无法将用户消息校验为可执行断点命令',
                    'args': {'message': f'我还在等待当前断点确认，但无法安全执行这条消息：{last_error}'},
                }
            ],
            'reply': f'我还在等待当前断点确认，但无法安全执行这条消息：{last_error}',
        },
        prompt,
        raw,
    )


def _planner_prompt(message: str, ctx: PlanContext) -> str:
    cap_summary = '\n'.join(
        (f"- {c['op']} (flow={c['flow']}, safety={c['safety']})" for c in ctx.capabilities_with_safety)
    )
    artifact_hint = ''
    if ctx.thread_state_summary:
        artifact_hint = (
            f'\n\nCurrent thread artifacts:\n{ctx.thread_state_summary}\n\n'
            "When user refers to '刚才的/最新的/上一个', use these artifact IDs."
        )
    return (
        f'User message: {message}{artifact_hint}\n\n'
        f'Available operations:\n{cap_summary}\n\n'
        "You are a task planner. Map the user's natural language request to operations.\n"
        'Rules:\n'
        '- For interruption/retry/re-run requests, prefer task.stop_active/task.continue_latest '
        'plus the restart op.\n'
        '- If user says a dataset is bad and asks to regenerate while analysis is running, '
        'emit task.stop_active(flow=run) before dataset_gen.start.\n'
        "- '创建评测集/生成数据集' -> dataset_gen.start with kb_id, eval_name\n"
        "- '评测/跑评测/生成报告' -> eval.run with dataset_id, target_chat_url; "
        'if user mentions dataset_name/数据集名/alias, put it in args.options.dataset_name\n'
        "- '分析/诊断' -> run.start with eval_id\n"
        "- '修改代码/apply' -> apply.start with report_id. apply already loops code edits "
        'and unit tests; do not emit multiple apply.start for one report.\n'
        "- 'ABTest/对比' -> abtest.create with apply_id, baseline_eval_id, dataset_id only "
        'after the apply is succeeded/accepted and its final unit-test round passed.\n'
        '- Extract specific IDs from artifacts when user refers to them\n'
        'Reply in strict JSON only, with reply first so it can be streamed: '
        '{"reply":"user-facing Chinese reply","ops":[{"op":"...","reason":"...","args":{...}}]}'
    )


def _checkpoint_prompt(message: str, ctx: PlanContext, last_error: str = '') -> str:
    checkpoint = (ctx.thread_state or {}).get('pending_checkpoint') or {}
    return (
        f'User message: {message}\n\n'
        f'Pending checkpoint:\n{json.dumps(checkpoint, ensure_ascii=False, indent=2)}\n\n'
        f'Thread state summary:\n{ctx.thread_state_summary}\n\n'
        'You are a checkpoint intent agent. Decide exactly one structured command.\n'
        'Allowed commands:\n'
        '- checkpoint.continue: user wants to continue the saved next_op.\n'
        '- checkpoint.rewind: user wants to rerun from a stage. Args: to_stage in '
        '[dataset_gen, eval, run, apply, abtest], optional input_patch for thread inputs '
        'such as num_cases, kb_id, algo_id, eval_name, target_chat_url, dataset_name. '
        'For run/apply reruns, put user analysis or modification feedback in input_patch.extra_instructions.\n'
        '- checkpoint.answer: user asks a question or requests explanation; do not advance.\n'
        '- checkpoint.cancel: user wants to stop waiting at this checkpoint.\n\n'
        'Return strict JSON only, with reply first so it can be streamed: '
        '{"reply":"user-facing Chinese reply","ops":[{"op":"checkpoint.continue|checkpoint.rewind|'
        'checkpoint.answer|checkpoint.cancel","reason":"...","args":{...}}]}\n'
        f"{('Previous validation error: ' + last_error) if last_error else ''}"
    )


class _ReplyDeltaExtractor:
    def __init__(self) -> None:
        self._prefix = ''
        self._in_reply = False
        self._done = False
        self._escape = ''
        self.text = ''

    def feed(self, chunk: str) -> str:
        out: list[str] = []
        for ch in chunk:
            if self._done:
                continue
            if not self._in_reply:
                self._prefix += ch
                m = re.search(r'"reply"\s*:\s*"', self._prefix)
                if m:
                    self._in_reply = True
                    rest = self._prefix[m.end():]
                    self._prefix = ''
                    if rest:
                        out.append(self.feed(rest))
                continue
            if self._escape:
                self._escape += ch
                decoded = self._decode_escape_if_complete()
                if decoded is None:
                    continue
                out.append(decoded)
                self.text += decoded
                self._escape = ''
                continue
            if ch == '\\':
                self._escape = '\\'
                continue
            if ch == '"':
                self._done = True
                continue
            out.append(ch)
            self.text += ch
        return ''.join(out)

    def _decode_escape_if_complete(self) -> str | None:
        if self._escape.startswith('\\u') and len(self._escape) < 6:
            return None
        if len(self._escape) < 2:
            return None
        try:
            return json.loads(f'"{self._escape}"')
        except Exception:
            return self._escape[-1]


def _checkpoint_autooperator_plan(message: str, checkpoint: dict[str, Any]) -> dict[str, Any] | None:
    text = message.strip()
    if not checkpoint:
        return None
    if text.startswith('继续执行'):
        return {
            'ops': [{'op': 'checkpoint.continue', 'reason': text, 'args': {}}],
            'reply': '好的，继续执行下一步。',
        }
    if text.startswith('当前分析报告的自动修改建议证据不足，请回退到 run 重新分析'):
        return {
            'ops': [
                {
                    'op': 'checkpoint.rewind',
                    'reason': '自动检测到报告建议证据不足，回退 run 重新分析',
                    'args': {
                        'to_stage': 'run',
                        'input_patch': {
                            'extra_instructions': '请重新分析并补充证据，提高自动修改建议的置信度和有效性。'
                        },
                    },
                }
            ],
            'reply': '好的，回退到 run 重新分析并补充证据。',
        }
    if text.startswith('回退到 apply 重新修改代码'):
        extra = _message_suffix(text, '要求：') or text
        return {
            'ops': [
                {
                    'op': 'checkpoint.rewind',
                    'reason': '自动检测到 apply 结果需要重新修改',
                    'args': {'to_stage': 'apply', 'input_patch': {'extra_instructions': extra}},
                }
            ],
            'reply': '好的，回退到 apply 并按补充要求重新修改。',
        }
    return None


def _message_suffix(text: str, marker: str) -> str:
    if marker not in text:
        return ''
    return text.split(marker, 1)[1].strip()


def _validate_checkpoint_boundary(op: str, args: dict[str, Any], ctx: PlanContext) -> None:
    if op not in {'checkpoint.continue', 'checkpoint.rewind', 'checkpoint.answer', 'checkpoint.cancel'}:
        raise ValueError(f'unsupported checkpoint command {op!r}')
    checkpoint = (ctx.thread_state or {}).get('pending_checkpoint')
    if not checkpoint:
        raise ValueError('no pending checkpoint')
    if op == 'checkpoint.continue' and not checkpoint.get('next_op'):
        raise ValueError('checkpoint has no next_op to continue')
    if op == 'checkpoint.rewind':
        stage = args.get('to_stage')
        if stage not in (checkpoint.get('allowed_stages') or []):
            raise ValueError(f'rewind stage {stage!r} is not allowed')
        patch = args.get('input_patch') or {}
        if not isinstance(patch, dict):
            raise ValueError('input_patch must be an object')
        allowed = {
            'num_cases',
            'kb_id',
            'algo_id',
            'eval_name',
            'target_chat_url',
            'dataset_name',
            'extra_instructions',
            'max_workers',
            'filters',
        }
        extra = sorted(set(patch) - allowed)
        if extra:
            raise ValueError(f'unsupported input_patch fields: {extra}')
        if 'num_cases' in patch:
            n = int(patch['num_cases'])
            if n < 1 or n > 200:
                raise ValueError('num_cases must be between 1 and 200')


def _parse_json_object(raw: Any) -> dict[str, Any]:
    if isinstance(raw, list):
        raw = raw[-1] if raw else {}
    if isinstance(raw, dict):
        return dict(raw)
    if not isinstance(raw, str):
        return dict(raw)
    text = raw.strip()
    fenced = re.search('```(?:json)?\\s*(.*?)```', text, re.S | re.I)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find('{')
        end = text.rfind('}')
        if start >= 0 and end > start:
            candidate = text[start: end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                try:
                    from json_repair import repair_json

                    return json.loads(repair_json(candidate))
                except Exception:
                    pass
        from json_repair import repair_json

        return json.loads(repair_json(text))


def _validate_abtest_boundary(payload: dict[str, Any], ctx: PlanContext) -> None:
    apply_id = payload.get('apply_id')
    state = ctx.thread_state or {}
    latest = state.get('latest_tasks') or {}
    apply_row = latest.get('apply') or {}
    if apply_row.get('id') == apply_id and (not _apply_row_ready(apply_row)):
        raise ValueError('abtest.create requires a succeeded apply with final tests passed')
    for row in state.get('active_tasks') or []:
        if row.get('flow') != 'abtest':
            continue
        rp = row.get('payload') or {}
        if (
            rp.get('apply_id') == apply_id
            and rp.get('baseline_eval_id') == payload.get('baseline_eval_id')
            and (rp.get('dataset_id') == payload.get('dataset_id'))
            and ((rp.get('eval_options') or {}) == (payload.get('eval_options') or {}))
        ):
            raise ValueError('matching abtest is already running')


def _apply_row_ready(row: dict[str, Any]) -> bool:
    result = (row.get('payload') or {}).get('result') or {}
    if row.get('status') not in {'succeeded', 'accepted'}:
        return False
    return result.get('status') == 'SUCCEEDED' and bool(row.get('final_commit') or result.get('final_commit'))


def _heuristic_plan(message: str, ctx: PlanContext) -> dict[str, Any] | None:
    message.lower()
    state = ctx.thread_state or {}
    inputs = state.get('inputs') or {}
    latest = state.get('latest_tasks') or {}
    active = state.get('active_tasks') or []
    flow = _flow_from_text(message)
    if any((k in message for k in ('拒绝修改', '拒绝代码', '不接受修改', 'reject apply', 'reject code'))):
        task_id = _latest_task_id(latest, 'apply')
        if task_id:
            return {
                'ops': [{'op': 'apply.reject', 'reason': '拒绝最近一次代码修改结果', 'args': {'task_id': task_id}}],
                'reply': '我会拒绝最近一次代码修改结果。',
            }
    if any((k in message for k in ('接受修改', '接受代码', '确认修改', '同意修改', 'accept apply', 'accept code'))):
        task_id = _latest_task_id(latest, 'apply')
        if task_id:
            return {
                'ops': [{'op': 'apply.accept', 'reason': '接受最近一次代码修改结果', 'args': {'task_id': task_id}}],
                'reply': '我会接受最近一次代码修改结果。',
            }
    if _wants_cancel_restart(message):
        ops = _cancel_restart_ops(flow, latest, active)
        if ops:
            return {'ops': ops, 'reply': '我会先取消当前相关任务，然后按原参数重新开始。'}
    if _wants_thread_retry(message):
        return {
            'ops': [{'op': 'thread.retry', 'reason': '重试当前整个 thread 最近可恢复任务', 'args': {}}],
            'reply': '我会重试当前线程最近可恢复的任务，并继续推进后续流程。',
        }
    if any((k in message for k in ('重试', '续跑', '继续执行', '继续跑', 'retry'))):
        if _latest_cancelled(latest):
            return {
                'ops': [],
                'reply': '当前线程最近的任务已经被取消，取消是终态，不能直接继续。请明确要求重新开始或重试整个线程。',
            }
        return {
            'ops': [
                {
                    'op': 'task.continue_latest',
                    'reason': '续跑最近暂停或瞬时失败的任务',
                    'args': {'flow': flow} if flow else {},
                }
            ],
            'reply': '我会续跑最近暂停或瞬时失败的任务。',
        }
    if any((k in message for k in ('取消', '终止', 'cancel'))):
        return {
            'ops': [{'op': 'task.cancel_active', 'reason': '取消当前活跃任务并取消线程流程', 'args': {'flow': flow} if flow else {}}],
            'reply': '我会取消当前正在执行的任务，并将线程标记为已取消。',
        }
    if any((k in message for k in ('暂停', '停止', '打断', 'stop'))):
        return {
            'ops': [{'op': 'task.stop_active', 'reason': '暂停当前活跃任务并暂停线程流程', 'args': {'flow': flow} if flow else {}}],
            'reply': '我会暂停当前正在执行的任务，并将线程标记为已暂停。',
        }
    if flow == 'eval':
        dataset_id = _extract_id_after(message, ('数据集', '评测集', 'dataset'))
        if dataset_id:
            return {
                'ops': [
                    {
                        'op': 'eval.run',
                        'reason': f'用户请求对数据集 {dataset_id} 发起评测',
                        'args': {'dataset_id': dataset_id},
                    }
                ],
                'reply': f'已对数据集 {dataset_id} 发起评测任务。',
            }
    if flow == 'dataset_gen' and any((k in message for k in ('生成', '创建', '构建'))):
        args = {
            'kb_id': _extract_named_id(message, 'kb_id') or inputs.get('kb_id'),
            'algo_id': _extract_named_id(message, 'algo_id') or inputs.get('algo_id') or 'general_algo',
            'eval_name': _extract_named_id(message, 'eval_name') or inputs.get('eval_name') or f'{ctx.thread_id}_eval',
        }
        num_cases = _extract_named_id(message, 'num_cases') or inputs.get('num_cases')
        if num_cases:
            args['num_cases'] = int(num_cases)
        if not args['kb_id']:
            return None
        return {
            'ops': [{'op': 'dataset_gen.start', 'reason': '基于当前线程输入生成评测集', 'args': args}],
            'reply': f"我会基于知识库 {args['kb_id']} 生成评测集 {args['eval_name']}。",
        }
    if flow == 'abtest':
        args = {
            'apply_id': _extract_named_id(message, 'apply_id') or _extract_id_after(message, ('apply',)),
            'baseline_eval_id': _extract_named_id(message, 'baseline_eval_id'),
            'dataset_id': _extract_named_id(message, 'dataset_id'),
        }
        eval_options: dict[str, Any] = {}
        dataset_name = _extract_named_id(message, 'dataset_name')
        kb_id = _extract_named_id(message, 'kb_id')
        max_workers = _extract_named_id(message, 'max_workers')
        if dataset_name:
            eval_options['dataset_name'] = dataset_name
        if kb_id:
            eval_options['filters'] = {'kb_id': kb_id}
        if max_workers and max_workers.isdigit():
            eval_options['max_workers'] = int(max_workers)
        if eval_options:
            args['eval_options'] = eval_options
        if args['apply_id'] and args['baseline_eval_id'] and args['dataset_id']:
            return {
                'ops': [{'op': 'abtest.create', 'reason': '按显式参数创建 ABTest', 'args': args}],
                'reply': '我会按给定参数创建 ABTest。',
            }
    if ('数据集' in message or '评测集' in message) and any(
        (k in message for k in ('重新生成', '重生成', '再生成', '生成有问题', '有问题'))
    ):
        ds = latest.get('dataset_gen') or {}
        payload = ds.get('payload') or {}
        args = {
            'kb_id': payload.get('kb_id') or _latest_artifact(state, 'kb_id'),
            'algo_id': payload.get('algo_id') or 'general_algo',
            'eval_name': _regen_name(
                payload.get('eval_name') or _latest_artifact(state, 'dataset_ids') or 'regen_eval'
            ),
        }
        if payload.get('num_cases'):
            args['num_cases'] = payload['num_cases']
        if not args['kb_id']:
            return None
        ops: list[dict[str, Any]] = []
        if _has_active_flow(active, 'run'):
            ops.append(
                {
                    'op': 'task.stop_active',
                    'reason': '先暂停当前分析，避免继续基于错误数据集诊断',
                    'args': {'flow': 'run'},
                }
            )
        ops.append({'op': 'dataset_gen.start', 'reason': '重新生成评测集', 'args': args})
        return {'ops': ops, 'reply': '我会先暂停当前分析，然后重新生成评测集。'}
    return None


def _flow_from_text(message: str) -> str | None:
    if any((k in message for k in ('abtest', 'ab test', '对比'))):
        return 'abtest'
    if any((k in message for k in ('分析', '诊断', 'run'))):
        return 'run'
    if '评测' in message and '评测集' not in message or any((k in message for k in ('跑评测', '发起评测', 'eval'))):
        return 'eval'
    if any((k in message for k in ('评测集', '数据集', 'dataset'))):
        return 'dataset_gen'
    if any((k in message for k in ('修改', 'apply'))):
        return 'apply'
    return None


def _has_active_flow(active: list[dict[str, Any]], flow: str) -> bool:
    return any((t.get('flow') == flow and t.get('status') == 'running' for t in active))


def _latest_artifact(state: dict[str, Any], key: str) -> str | None:
    vals = (state.get('artifacts') or {}).get(key) or []
    return vals[-1] if vals else None


def _latest_task_id(latest: dict[str, Any], flow: str) -> str | None:
    row = latest.get(flow) or {}
    return row.get('id')


def _latest_cancelled(latest: dict[str, Any]) -> bool:
    rows = [row for row in latest.values() if isinstance(row, dict) and row.get('created_at')]
    if not rows:
        return False
    rows.sort(key=lambda row: row.get('created_at', 0.0), reverse=True)
    return rows[0].get('status') == 'cancelled'


def _wants_cancel_restart(message: str) -> bool:
    return any(
        (
            k in message
            for k in ('取消后重新', '取消后重启', '取消并重新', '取消再重新', 'cancel and restart', '重新开始')
        )
    )


def _wants_thread_retry(message: str) -> bool:
    return any((k in message for k in ('重试整个thread', '重试整个线程', '重试当前线程', '重试当前整个流程', '重试整个流程')))


def _extract_id_after(message: str, markers: tuple[str, ...]) -> str | None:
    for marker in markers:
        m = re.search(re.escape(marker) + '\\s*([A-Za-z0-9_.:-]+)', message, re.I)
        if m:
            return m.group(1).strip('，。,. ')
    return None


def _extract_named_id(message: str, name: str) -> str | None:
    pattern = f'{re.escape(name)}\\s*[:=：]?\\s*([A-Za-z0-9_.:/-]+)'
    m = re.search(pattern, message, re.I)
    return m.group(1).strip('，。,. ') if m else None


def _cancel_restart_ops(flow: str | None, latest: dict[str, Any], active: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not flow:
        return []
    ops: list[dict[str, Any]] = []
    if _has_active_flow(active, flow):
        ops.append({'op': 'task.cancel_active', 'reason': f'取消当前 {flow} 任务', 'args': {'flow': flow}})
    start = _restart_op(flow, latest.get(flow) or {})
    if start:
        ops.append(start)
    return ops


def _restart_op(flow: str, row: dict[str, Any]) -> dict[str, Any] | None:
    payload = dict(row.get('payload') or {})
    if flow == 'dataset_gen':
        args = {
            'kb_id': payload.get('kb_id'),
            'algo_id': payload.get('algo_id') or 'general_algo',
            'eval_name': _regen_name(payload.get('eval_name') or 'regen_eval'),
        }
        if payload.get('num_cases'):
            args['num_cases'] = payload['num_cases']
        return {'op': 'dataset_gen.start', 'reason': '重新生成评测集', 'args': args} if args['kb_id'] else None
    if flow == 'eval':
        args = {
            'thread_id': row.get('thread_id'),
            'dataset_id': payload.get('dataset_id'),
            'eval_id': payload.get('eval_id'),
            'target_chat_url': payload.get('target_chat_url'),
            'options': payload.get('eval_options') or {},
        }
        return (
            {
                'op': 'eval.run' if args.get('dataset_id') else 'eval.fetch',
                'reason': '重新执行评测任务',
                'args': {k: v for (k, v) in args.items() if v},
            }
            if args.get('dataset_id') or args.get('eval_id')
            else None
        )
    if flow == 'run':
        args = {k: payload[k] for k in ('eval_id', 'badcase_limit', 'score_field') if k in payload}
        return {'op': 'run.start', 'reason': '重新启动分析流程', 'args': args}
    if flow == 'apply':
        args = {'report_id': row.get('report_id') or payload.get('report_id')}
        return {'op': 'apply.start', 'reason': '重新启动代码修改', 'args': args} if args['report_id'] else None
    if flow == 'abtest':
        return {'op': 'abtest.create', 'reason': '重新启动 ABTest', 'args': payload} if payload else None
    return None


def _regen_name(name: str) -> str:
    base = re.sub('[^A-Za-z0-9_.-]+', '_', name).strip('_') or 'regen_eval'
    return f"{base}_regen_{time.strftime('%H%M%S')}"
