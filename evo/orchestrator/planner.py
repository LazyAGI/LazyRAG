from __future__ import annotations
import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator
from evo.orchestrator import capabilities as caps
from evo.service.core import schemas
from evo.service.core.intent_store import Intent, IntentPreview, PlanResult

FLOWS = ('dataset_gen', 'eval', 'run', 'apply', 'abtest')
SCHEMAS = {
    'run.start': schemas.RunCreate, 'apply.start': schemas.ApplyCreate,
    'dataset_gen.start': schemas.DatasetGenCreate, 'eval.run': schemas.EvalCreate,
    'eval.fetch': schemas.EvalCreate, 'abtest.create': schemas.AbtestCreate,
    'checkpoint.continue': schemas.CheckpointContinue, 'checkpoint.rewind': schemas.CheckpointRewind,
    'checkpoint.answer': schemas.CheckpointAnswer, 'checkpoint.cancel': schemas.CheckpointCancel,
}


@dataclass
class PlanContext:
    thread_id: str
    recent_history: list[tuple[str, str]] = field(default_factory=list)
    thread_state_summary: str = ''
    capabilities_with_safety: list[dict] = field(default_factory=list)
    thread_state: dict[str, Any] = field(default_factory=dict)


@dataclass
class Draft:
    reply: str
    ops: list[dict[str, Any]]
    source: str
    prompt: str = ''
    raw: Any = None


class State:
    def __init__(self, ctx: PlanContext) -> None:
        self.ctx = ctx
        self.data = ctx.thread_state or {}
        self.inputs = self.data.get('inputs') or {}
        self.latest = self.data.get('latest_tasks') or {}
        self.active = self.data.get('active_tasks') or []
        self.artifacts = self.data.get('artifacts') or {}
        self.checkpoint = self.data.get('pending_checkpoint') or {}

    def latest_id(self, flow: str) -> str | None:
        return (self.latest.get(flow) or {}).get('id')

    def latest_payload(self, flow: str) -> dict:
        return dict((self.latest.get(flow) or {}).get('payload') or {})

    def artifact(self, key: str) -> str | None:
        vals = self.artifacts.get(key) or []
        return str(vals[-1]) if vals else None

    def success(self, flow: str) -> bool:
        return (self.latest.get(flow) or {}).get('status') in {'succeeded', 'accepted'}

    def active_flow(self, flow: str | None) -> bool:
        return any(t.get('status') == 'running' and (not flow or t.get('flow') == flow) for t in self.active)


class Planner:
    def __init__(self, *, llm: Callable[[str], Any],
                 stream_llm: Callable[[str, Callable[[], bool]], Iterator[str]] | None = None) -> None:
        self.llm = llm
        self.stream_llm = stream_llm

    def draft(self, message: str, ctx: PlanContext) -> Intent:
        return self._intent(message, ctx, self._draft(message, ctx))

    def draft_stream(self, message: str, ctx: PlanContext, cancel_requested: Callable[[], bool]) -> Iterator[dict[str, Any]]:
        if self.stream_llm is None:
            yield {'type': 'final', 'intent': self.draft(message, ctx)}
            return
        state = State(ctx)
        prompt = _prompt(message, ctx, checkpoint=bool(state.checkpoint))
        parsed, raw, emitted = yield from _stream_plan(self.stream_llm, prompt, cancel_requested)
        intent = self._intent(message, ctx, _draft_from_parsed(parsed, _source(state), prompt, raw))
        suffix = intent.reply[len(emitted):] if emitted and intent.reply.startswith(emitted) else intent.reply
        if suffix:
            yield {'type': 'reply_delta', 'delta': suffix}
        yield {'type': 'final', 'intent': intent}

    def materialize(self, intent: Intent, ctx: PlanContext, user_edit: dict | None = None) -> PlanResult:
        raw_ops = user_edit.get('ops', []) if user_edit else [
            {'op': p.op, 'args': p.params_summary} for p in intent.suggested_ops_preview]
        ops, validation, warnings = [], [], []
        for item in raw_ops:
            op, args = (item or {}).get('op'), dict((item or {}).get('args') or {})
            try:
                caps.validate(op, args)
                _validate(op, args, ctx)
                ops.append({'op': op, 'args': args})
                validation.append({'op': op, 'args': args, 'status': 'accepted'})
            except Exception as exc:
                warnings.append(f'validation failed: {exc}')
                validation.append({'op': op, 'args': args, 'status': 'rejected', 'error': str(exc)})
        return PlanResult(intent_id=intent.intent_id, ops=ops, warnings=warnings,
                          trace={'raw_ops': raw_ops, 'validation': validation})

    def _draft(self, message: str, ctx: PlanContext) -> Draft:
        state = State(ctx)
        prompt = _prompt(message, ctx, checkpoint=bool(state.checkpoint))
        try:
            return _draft_from_parsed(_parse_json(self.llm(prompt)), _source(state), prompt, None)
        except Exception as exc:
            msg = f'我还在等待当前断点确认，但无法安全执行这条消息：{exc}' if state.checkpoint else f'收到：{message}。暂无可自动执行的操作。'
            op = {'op': 'checkpoint.answer', 'reason': '回答断点问题', 'args': {'message': msg}} if state.checkpoint else None
            return Draft(msg, [op] if op else [], 'fallback', prompt, {'error': str(exc)})

    def _intent(self, message: str, ctx: PlanContext, draft: Draft) -> Intent:
        state = State(ctx)
        previews, warnings = [], []
        for item in _normalize(draft.ops, ctx, state):
            op, args = item.get('op', ''), item.get('args') or {}
            if op not in caps.REGISTRY:
                warnings.append(f'unknown op: {op}')
                continue
            cap = caps.get(op)
            previews.append(IntentPreview(op, item.get('reason') or f'{cap.flow}: {cap.description}', cap.safety, args))
        reply = draft.reply or f'收到：{message}。'
        if previews and previews[0].op not in {'checkpoint.answer', 'checkpoint.cancel'} and not state.checkpoint.get('terminal'):
            reply += ' 我会在后台执行，并把过程写入事件流。'
        return Intent(intent_id=f'intent_{ctx.thread_id}_{uuid.uuid4().hex[:8]}', thread_id=ctx.thread_id,
                      user_message=message, reply=reply, suggested_ops_preview=previews, requires_confirm=False,
                      trace={'source': draft.source, 'prompt': draft.prompt, 'raw_answer': draft.raw,
                             'parsed': {'reply': draft.reply, 'ops': draft.ops}, 'warnings': warnings})


def _source(state: State) -> str:
    return 'checkpoint_llm' if state.checkpoint else 'llm'


def _normalize(ops: list[dict[str, Any]], ctx: PlanContext, state: State) -> list[dict[str, Any]]:
    out = []
    for item in ops or []:
        op, args = item.get('op'), dict(item.get('args') or {})
        if state.checkpoint and op in {'task.continue_latest', 'thread.retry'}:
            op, args = 'checkpoint.continue', {}
        if op == 'eval.run':
            if args.get('eval_id') and not args.get('dataset_id'):
                op = 'eval.fetch'
            if args.get('dataset_id'):
                args.pop('eval_id', None)
            _fill_eval(args, state.inputs)
        elif op == 'run.start':
            args.setdefault('eval_id', state.latest_id('eval') if state.success('eval') else None)
        elif op == 'apply.start':
            args.setdefault('report_id', state.latest_payload('run').get('report_id') or (state.latest.get('run') or {}).get('report_id'))
        elif op == 'abtest.create':
            _fill_abtest(args, state)
        elif op == 'dataset_gen.start':
            args.setdefault('kb_id', state.inputs.get('kb_id'))
            args.setdefault('algo_id', state.inputs.get('algo_id') or 'general_algo')
            args.setdefault('eval_name', state.inputs.get('eval_name') or f'{ctx.thread_id}_eval')
        out.append({'op': op, 'reason': item.get('reason', ''), 'args': {k: v for k, v in args.items() if v is not None}})
    return out


def _fill_eval(args: dict, inputs: dict) -> None:
    args.setdefault('target_chat_url', inputs.get('target_chat_url'))
    options = dict(args.get('options') or args.get('eval_options') or {})
    if inputs.get('dataset_name'):
        options.setdefault('dataset_name', inputs['dataset_name'])
    if options:
        args['options'] = options
    args.pop('eval_options', None)


def _fill_abtest(args: dict, state: State) -> None:
    args.setdefault('apply_id', state.latest_id('apply'))
    args.setdefault('baseline_eval_id', state.latest_id('eval'))
    args.setdefault('dataset_id', state.artifact('dataset_ids'))
    args.setdefault('target_chat_url', state.inputs.get('target_chat_url'))
    if state.inputs.get('dataset_name'):
        args.setdefault('eval_options', {}).setdefault('dataset_name', state.inputs['dataset_name'])


def _validate(op: str, args: dict, ctx: PlanContext) -> None:
    payload = {**args, 'thread_id': ctx.thread_id}
    if model := SCHEMAS.get(op):
        model(**payload)
    state = State(ctx)
    if state.checkpoint and not op.startswith('checkpoint.'):
        raise ValueError('pending checkpoint only accepts checkpoint.* ops')
    if op in {'task.continue_latest', 'thread.retry'} and not _has_resumable(state, args):
        raise ValueError('no paused or transient failed task to continue')
    if op.startswith('checkpoint.'):
        _validate_checkpoint(op, args, state.checkpoint)
    if op == 'abtest.create' and (row := state.latest.get('apply') or {}).get('id') == args.get('apply_id') and not _apply_ready(row):
        raise ValueError('abtest.create requires a succeeded apply with final tests passed')


def _validate_checkpoint(op: str, args: dict, checkpoint: dict) -> None:
    if not checkpoint:
        raise ValueError('no pending checkpoint')
    if op == 'checkpoint.continue' and not checkpoint.get('next_op') and not checkpoint.get('terminal'):
        raise ValueError('checkpoint has no next_op to continue')
    if op == 'checkpoint.rewind' and args.get('to_stage') not in (checkpoint.get('allowed_stages') or FLOWS):
        raise ValueError(f"rewind stage {args.get('to_stage')!r} is not allowed")


def _prompt(message: str, ctx: PlanContext, *, checkpoint: bool) -> str:
    return (f'User message: {message}\n\nState:\n{ctx.thread_state_summary}\n\nCapabilities:\n{_caps(ctx)}\n\n'
            f'You are the Evo {"checkpoint" if checkpoint else "planner"} intent agent. Return strict JSON only: '
            '{"reply":"Chinese user-facing reply","ops":[{"op":"registered.op","reason":"short reason","args":{}}]}\n'
            'Use checkpoint.* only when pending_checkpoint exists. Prefer exact user intent; do not invent IDs. '
            'For retry/续跑/继续执行, resume the latest paused or transient failed task with task.continue_latest; '
            'restart a stage only when the user explicitly asks to rerun that named stage.')


def _draft_from_parsed(parsed: dict, source: str, prompt: str, raw: Any) -> Draft:
    return Draft(str(parsed.get('reply') or ''), list(parsed.get('ops') or []), source, prompt, raw if raw is not None else parsed)


def _stream_plan(stream_llm, prompt: str, cancel_requested) -> Iterator[tuple[dict, Any, str]]:
    parts, reply = [], _ReplyDeltaExtractor()
    for chunk in stream_llm(prompt, cancel_requested):
        if cancel_requested():
            raise RuntimeError('MESSAGE_CANCELLED')
        parts.append(str(chunk or ''))
        if delta := reply.feed(str(chunk or '')):
            yield {'type': 'reply_delta', 'delta': delta}
    raw = ''.join(parts)
    return _parse_json(raw), raw, reply.text


class _ReplyDeltaExtractor:
    def __init__(self) -> None:
        self.buf = ''
        self.text = ''
        self.on = False
        self.done = False
        self.esc = ''

    def feed(self, chunk: str) -> str:
        out = []
        for ch in chunk:
            if self.done:
                continue
            if not self.on:
                self.buf += ch
                if m := re.search(r'"reply"\s*:\s*"', self.buf):
                    self.on = True
                    out.append(self.feed(self.buf[m.end():]))
                continue
            if self.esc:
                self.esc += ch
                if self.esc.startswith('\\u') and len(self.esc) < 6:
                    continue
                val = _json_string(self.esc)
                out.append(val)
                self.text += val
                self.esc = ''
                continue
            if ch == '\\':
                self.esc = '\\'
            elif ch == '"':
                self.done = True
            else:
                out.append(ch)
                self.text += ch
        return ''.join(out)


def _apply_ready(row: dict) -> bool:
    result = (row.get('payload') or {}).get('result') or {}
    return row.get('status') in {'succeeded', 'accepted'} and result.get('status') == 'SUCCEEDED' and bool(row.get('final_commit') or result.get('final_commit'))


def _has_resumable(state: State, args: dict) -> bool:
    flow, task_id = args.get('flow'), args.get('task_id')
    return any(
        row.get('status') in {'paused', 'failed_transient'} and
        (not flow or row.get('flow') == flow) and
        (not task_id or row.get('id') == task_id)
        for row in state.latest.values()
    )


def _caps(ctx: PlanContext) -> str:
    return '\n'.join(f"- {c['op']} flow={c['flow']} safety={c['safety']}" for c in ctx.capabilities_with_safety)


def _parse_json(raw: Any) -> dict:
    if isinstance(raw, list):
        raw = raw[-1] if raw else {}
    if isinstance(raw, dict):
        return dict(raw)
    text = str(raw or '').strip()
    if m := re.search('```(?:json)?\\s*(.*?)```', text, re.S | re.I):
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        s, e = text.find('{'), text.rfind('}')
        candidate = text[s:e + 1] if s >= 0 and e > s else text
        try:
            from json_repair import repair_json
            return json.loads(repair_json(candidate))
        except Exception:
            return json.loads(candidate)


def _json_string(value: str) -> str:
    try:
        return json.loads(f'"{value}"')
    except Exception:
        return value[-1]
