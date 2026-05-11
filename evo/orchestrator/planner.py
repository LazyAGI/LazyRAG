from __future__ import annotations
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator
from evo.orchestrator import capabilities as caps
from evo.service.core import schemas
from evo.service.core.intent_store import Intent, IntentPreview, PlanResult

FLOWS = ('dataset_gen', 'eval', 'run', 'apply', 'abtest')
STEP_FLOW = {'1': 'dataset_gen', '一': 'dataset_gen', '2': 'eval', '二': 'eval', '两': 'eval',
             '3': 'run', '三': 'run', '4': 'apply', '四': 'apply', '5': 'abtest', '五': 'abtest'}
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
        if rule := _rule_plan(message, ctx, state):
            intent = self._intent(message, ctx, rule)
            if intent.reply:
                yield {'type': 'reply_delta', 'delta': intent.reply}
            yield {'type': 'final', 'intent': intent}
            return
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
        if rule := _rule_plan(message, ctx, state):
            return rule
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


def _rule_plan(message: str, ctx: PlanContext, state: State) -> Draft | None:
    text, flow = message.strip(), _flow(message)
    if state.checkpoint:
        return _checkpoint_rule(text, state)
    if _has(text, '拒绝修改', '拒绝代码', '不接受修改', 'reject apply', 'reject code') and state.latest_id('apply'):
        return _one('我会拒绝最近一次代码修改结果。', 'apply.reject', '拒绝最近一次代码修改结果', {'task_id': state.latest_id('apply')}, 'rule')
    if _has(text, '接受修改', '接受代码', '确认修改', '同意修改', 'accept apply', 'accept code') and state.latest_id('apply'):
        return _one('我会接受最近一次代码修改结果。', 'apply.accept', '接受最近一次代码修改结果', {'task_id': state.latest_id('apply')}, 'rule')
    if _has(text, '取消后重新', '取消并重新', '取消再重新', 'cancel and restart') and flow:
        return _restart(flow, state, cancel=True)
    if flow and _has(text, '重新执行', '重新跑', '重跑', '重新启动', '重新发起', 'rerun', 'restart'):
        return _restart(flow, state)
    if _has(text, '重试整个thread', '重试整个线程', '重试当前线程', '重试当前整个流程', '重试整个流程'):
        return _one('我会重试当前线程最近可恢复的任务，并继续推进后续流程。', 'thread.retry', '重试当前整个 thread', {}, 'rule')
    if _has(text, '继续下一步', '下一步', '下一个步骤', '继续后续流程', '推进流程'):
        return _next_step(state)
    if text.startswith('继续执行'):
        return _next_step(state) or Draft('当前流程已结束。如需重试，请说明要重新执行第几步。', [], 'rule')
    if _has(text, '重试', '续跑', '继续执行', '继续跑', 'retry'):
        return _one('我会续跑最近暂停或瞬时失败的任务。', 'task.continue_latest', '续跑最近暂停或瞬时失败的任务', {'flow': flow} if flow else {}, 'rule')
    if _has(text, '取消', '终止', 'cancel'):
        return _one('我会取消当前正在执行的任务，并将线程标记为已取消。', 'task.cancel_active', '取消当前活跃任务', {'flow': flow} if flow else {}, 'rule')
    if _has(text, '暂停', '停止', '打断', 'stop'):
        return _one('我会暂停当前正在执行的任务，并将线程标记为已暂停。', 'task.stop_active', '暂停当前活跃任务', {'flow': flow} if flow else {}, 'rule')
    if flow == 'eval' and (dataset_id := _extract_after(text, '数据集', '评测集', 'dataset')):
        return _one(f'已对数据集 {dataset_id} 发起评测任务。', 'eval.run', f'评测数据集 {dataset_id}', {'dataset_id': dataset_id}, 'rule')
    if flow == 'dataset_gen' and _has(text, '生成', '创建', '构建'):
        args = {'kb_id': _named(text, 'kb_id') or state.inputs.get('kb_id'),
                'algo_id': _named(text, 'algo_id') or state.inputs.get('algo_id') or 'general_algo',
                'eval_name': _named(text, 'eval_name') or state.inputs.get('eval_name') or f'{ctx.thread_id}_eval'}
        if n := _named(text, 'num_cases') or state.inputs.get('num_cases'):
            args['num_cases'] = int(n)
        if args['kb_id']:
            return _one(f"我会基于知识库 {args['kb_id']} 生成评测集 {args['eval_name']}。", 'dataset_gen.start', '基于当前线程输入生成评测集', args, 'rule')
    return None


def _checkpoint_rule(text: str, state: State) -> Draft | None:
    cp, flow = state.checkpoint, _flow(text)
    if text.startswith('继续执行'):
        return _one('好的，当前流程已结束。' if cp.get('terminal') else '好的，继续执行下一步。', 'checkpoint.continue', text, {}, 'checkpoint_rule')
    if _has(text, '取消', '终止'):
        return _one('好的，已取消当前断点等待。', 'checkpoint.cancel', text, {}, 'checkpoint_rule')
    if flow and _has(text, '重新执行', '重新跑', '重跑', '回退') and flow in (cp.get('allowed_stages') or FLOWS):
        patch = {'extra_instructions': _suffix(text, '要求：')} if _suffix(text, '要求：') else {}
        return _one(f'好的，回退到 {flow} 重新执行。', 'checkpoint.rewind', f'回退到 {flow}', {'to_stage': flow, 'input_patch': patch}, 'checkpoint_rule')
    return None


def _restart(flow: str, state: State, *, cancel: bool = False) -> Draft:
    start = _restart_op(flow, state)
    if not start:
        return Draft(f'当前线程没有可复用的 {flow} 任务参数，无法直接重新执行。', [], 'rule')
    ops = [{'op': 'task.cancel_active' if cancel else 'task.stop_active', 'reason': f'{"取消" if cancel else "停止"}当前 {flow} 任务', 'args': {'flow': flow}}] if state.active_flow(flow) else []
    return Draft('我会按最近一次任务参数重新执行。', ops + [start], 'rule')


def _restart_op(flow: str, state: State) -> dict | None:
    row, payload = state.latest.get(flow) or {}, state.latest_payload(flow)
    if flow == 'dataset_gen':
        args = {'kb_id': payload.get('kb_id') or state.inputs.get('kb_id'), 'algo_id': payload.get('algo_id') or state.inputs.get('algo_id') or 'general_algo', 'eval_name': _regen(payload.get('eval_name') or state.inputs.get('eval_name') or 'regen_eval')}
        if payload.get('num_cases') or state.inputs.get('num_cases'):
            args['num_cases'] = payload.get('num_cases') or state.inputs.get('num_cases')
        return {'op': 'dataset_gen.start', 'reason': '重新生成评测集', 'args': args} if args['kb_id'] else None
    if flow == 'eval':
        args = {'dataset_id': payload.get('dataset_id') or state.artifact('dataset_ids'), 'eval_id': payload.get('eval_id'), 'target_chat_url': payload.get('target_chat_url'), 'options': payload.get('eval_options') or payload.get('options') or {}}
        return {'op': 'eval.run' if args.get('dataset_id') else 'eval.fetch', 'reason': '重新执行评测任务', 'args': {k: v for k, v in args.items() if v}} if args.get('dataset_id') or args.get('eval_id') else None
    if flow == 'run':
        args = {k: payload[k] for k in ('eval_id', 'badcase_limit', 'score_field', 'extra_instructions') if k in payload}
        args.setdefault('eval_id', state.latest_id('eval') if state.success('eval') else None)
        return {'op': 'run.start', 'reason': '重新启动分析流程', 'args': {k: v for k, v in args.items() if v}} if args.get('eval_id') else None
    if flow == 'apply':
        rid = row.get('report_id') or payload.get('report_id') or state.latest_payload('run').get('report_id')
        return {'op': 'apply.start', 'reason': '重新启动代码修改', 'args': {'report_id': rid}} if rid else None
    if flow == 'abtest':
        return {'op': 'abtest.create', 'reason': '重新启动 ABTest', 'args': payload} if payload else None
    return None


def _next_step(state: State) -> Draft | None:
    dataset_id = state.artifact('dataset_ids')
    if dataset_id and not state.success('eval'):
        ops = [{'op': 'eval.cancel', 'reason': '取消指向旧数据集的失败评测任务', 'args': {'task_id': state.latest_id('eval')}}] if _stale_eval(state, dataset_id) else []
        ops.append({'op': 'eval.run', 'reason': '使用最新真实评测集继续评测', 'args': {'dataset_id': dataset_id}})
        return Draft('正在启动评测任务，使用最新生成的数据集进行评估。', ops, 'rule')
    if state.success('eval') and not state.success('run'):
        return _one('正在基于最新评测结果启动分析。', 'run.start', '基于最新评测结果继续分析', {'eval_id': state.latest_id('eval')}, 'rule')
    report_id = state.latest_payload('run').get('report_id') or (state.latest.get('run') or {}).get('report_id')
    if report_id and state.success('run') and not state.success('apply'):
        return _one('正在基于最新分析报告启动代码修改。', 'apply.start', '基于最新分析报告继续修改代码', {'report_id': report_id}, 'rule')
    return None


def _normalize(ops: list[dict[str, Any]], ctx: PlanContext, state: State) -> list[dict[str, Any]]:
    out = []
    for item in ops or []:
        op, args = item.get('op'), dict(item.get('args') or {})
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
            'Use checkpoint.* only when pending_checkpoint exists. Prefer exact user intent; do not invent IDs.')


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


def _one(reply: str, op: str, reason: str, args: dict, source: str) -> Draft:
    return Draft(reply, [{'op': op, 'reason': reason, 'args': args}], source)


def _flow(text: str) -> str | None:
    if m := re.search(r'第\s*([一二两三四五1-5])\s*(?:步|阶段|个流程|个步骤)', text):
        return STEP_FLOW.get(m.group(1))
    if _has(text, 'abtest', 'ab test', '对比'):
        return 'abtest'
    if _has(text, '分析', '诊断', 'run'):
        return 'run'
    if _has(text, '修改', 'apply'):
        return 'apply'
    if _has(text, '评测集', '数据集', 'dataset'):
        return 'dataset_gen'
    return 'eval' if ('评测' in text and '评测集' not in text) or _has(text, '跑评测', '发起评测', 'eval') else None


def _has(text: str, *keys: str) -> bool:
    return any(k in text for k in keys)


def _extract_after(text: str, *markers: str) -> str | None:
    for marker in markers:
        if m := re.search(re.escape(marker) + r'\s*([A-Za-z0-9_.:-]+)', text, re.I):
            return m.group(1).strip('，。,. ')
    return None


def _named(text: str, name: str) -> str | None:
    m = re.search(f'{re.escape(name)}\\s*[:=：]?\\s*([A-Za-z0-9_.:/-]+)', text, re.I)
    return m.group(1).strip('，。,. ') if m else None


def _suffix(text: str, marker: str) -> str:
    return text.split(marker, 1)[1].strip() if marker in text else ''


def _regen(name: str) -> str:
    return f"{re.sub('[^A-Za-z0-9_.-]+', '_', name).strip('_') or 'regen_eval'}_regen_{time.strftime('%H%M%S')}"


def _stale_eval(state: State, dataset_id: str) -> bool:
    row = state.latest.get('eval') or {}
    return row.get('status') in {'failed_transient', 'paused'} and (row.get('payload') or {}).get('dataset_id') != dataset_id


def _apply_ready(row: dict) -> bool:
    result = (row.get('payload') or {}).get('result') or {}
    return row.get('status') in {'succeeded', 'accepted'} and result.get('status') == 'SUCCEEDED' and bool(row.get('final_commit') or result.get('final_commit'))


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
