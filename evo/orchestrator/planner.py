from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable

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
    def __init__(self, *, llm: Callable[[str], Any]) -> None:
        self.llm = llm

    def draft(self, message: str, ctx: PlanContext) -> Intent:
        import uuid
        cap_summary = '\n'.join(
            f"- {c['op']} (flow={c['flow']}, safety={c['safety']})"
            for c in ctx.capabilities_with_safety[:20]
        )
        artifact_hint = ''
        prompt = ''
        raw_answer: Any = None
        source = 'heuristic'
        if ctx.thread_state_summary:
            artifact_hint = (
                f"\n\nCurrent thread artifacts:\n{ctx.thread_state_summary}\n\n"
                f"When user refers to '刚才的/最新的/上一个', use these artifact IDs."
            )
        parsed = _heuristic_plan(message, ctx)
        if parsed is None:
            source = 'llm'
            prompt = (
            f"User message: {message}{artifact_hint}\n\n"
            f"Available operations:\n{cap_summary}\n\n"
            f"You are a task planner. Map the user's natural language request to operations.\n"
            f"Rules:\n"
            f"- For interruption/retry/re-run requests, prefer task.stop_active/task.continue_latest plus the restart op.\n"
            f"- If user says a dataset is bad and asks to regenerate while analysis is running, emit task.stop_active(flow=run) before dataset_gen.start.\n"
            f"- '创建评测集/生成数据集' -> dataset_gen.start with kb_id, eval_name\n"
            f"- '评测/跑评测/生成报告' -> eval.run with dataset_id, target_chat_url; "
            f"if user mentions dataset_name/数据集名/alias, put it in args.options.dataset_name\n"
            f"- '分析/诊断' -> run.start with eval_id\n"
            f"- '修改代码/apply' -> apply.start with report_id. apply already loops code edits and unit tests; do not emit multiple apply.start for one report.\n"
            f"- 'ABTest/对比' -> abtest.create with apply_id, baseline_eval_id, dataset_id only after the apply is succeeded/accepted and its final unit-test round passed.\n"
            f"- Extract specific IDs from artifacts when user refers to them\n"
            f"Reply in strict JSON only: "
            f"{{\"ops\":[{{\"op\":\"...\",\"reason\":\"...\",\"args\":{{...}}}}],\"reply\":\"...\"}}"
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

        selected_ops = parsed.get('ops', [])
        previews: list[IntentPreview] = []
        warnings: list[str] = []
        for sel in selected_ops:
            op_name = sel.get('op', '')
            if not op_name or op_name not in caps.REGISTRY:
                warnings.append(f"unknown op: {op_name}")
                continue
            cap = caps.get(op_name)
            previews.append(IntentPreview(
                op=op_name,
                humanized=sel.get('reason', f'{cap.flow}: {cap.description}'),
                safety=cap.safety,
                params_summary=sel.get('args', {}),
            ))

        requires_confirm = False
        reply = parsed.get('reply', f'收到：{message}。')
        if previews:
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

    def materialize(self, intent: Intent, ctx: PlanContext,
                    user_edit: dict | None = None) -> PlanResult:
        ops: list[dict[str, Any]] = []
        warnings: list[str] = []
        raw_ops = user_edit.get('ops', []) if user_edit else None
        if raw_ops is None:
            raw_ops = [
                {'op': preview.op, 'args': preview.params_summary}
                for preview in intent.suggested_ops_preview
            ]
        validation_details: list[dict[str, Any]] = []
        for op_data in raw_ops:
            try:
                op_name = op_data['op']
                args = op_data.get('args', {})
                caps.validate(op_name, args)
                _validate_schema(op_name, args, ctx)
                ops.append({'op': op_name, 'args': args})
                validation_details.append({
                    'op': op_name, 'args': args, 'status': 'accepted',
                })
            except (KeyError, TypeError, ValueError) as exc:
                warnings.append(f"validation failed: {exc}")
                validation_details.append({
                    'op': op_data.get('op') if isinstance(op_data, dict) else None,
                    'args': op_data.get('args') if isinstance(op_data, dict) else None,
                    'status': 'rejected', 'error': str(exc),
                })
        return PlanResult(
            intent_id=intent.intent_id,
            ops=ops,
            warnings=warnings,
            trace={'raw_ops': raw_ops, 'validation': validation_details},
        )

    def _materialize_with_llm(self, intent: Intent,
                              ctx: PlanContext) -> list[dict[str, Any]]:
        preview = [
            {'op': p.op, 'args': p.params_summary, 'reason': p.humanized}
            for p in intent.suggested_ops_preview
        ]
        prompt = (
            f"Materialize executable operations for thread {ctx.thread_id}.\n"
            f"User message: {intent.user_message}\n\n"
            f"Recent history: {ctx.recent_history[-20:]}\n\n"
            f"Thread state:\n{ctx.thread_state_summary}\n\n"
            f"Draft preview: {preview}\n\n"
            f"Return strict JSON only: "
            f"{{\"ops\":[{{\"op\":\"eval.run\",\"args\":{{\"dataset_id\":\"...\",\"target_chat_url\":\"...\",\"options\":{{\"dataset_name\":\"...\"}}}}}}]}}"
        )
        try:
            raw = self.llm(prompt)
            parsed = _parse_json_object(raw)
            ops = parsed.get('ops') or []
            return ops if isinstance(ops, list) else []
        except Exception:
            return []


def _validate_schema(op: str, args: dict[str, Any], ctx: PlanContext) -> None:
    model_by_op = {
        'run.start': schemas.RunCreate,
        'apply.start': schemas.ApplyCreate,
        'dataset_gen.start': schemas.DatasetGenCreate,
        'eval.run': schemas.EvalCreate,
        'eval.fetch': schemas.EvalCreate,
        'abtest.create': schemas.AbtestCreate,
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


def _parse_json_object(raw: Any) -> dict[str, Any]:
    if isinstance(raw, list):
        raw = raw[-1] if raw else {}
    if isinstance(raw, dict):
        return dict(raw)
    if not isinstance(raw, str):
        return dict(raw)
    text = raw.strip()
    fenced = re.search(r'```(?:json)?\s*(.*?)```', text, re.S | re.I)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find('{')
        end = text.rfind('}')
        if start >= 0 and end > start:
            candidate = text[start:end + 1]
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
    if apply_row.get('id') == apply_id and not _apply_row_ready(apply_row):
        raise ValueError('abtest.create requires a succeeded apply with final tests passed')
    for row in state.get('active_tasks') or []:
        if row.get('flow') != 'abtest':
            continue
        rp = row.get('payload') or {}
        if (
            rp.get('apply_id') == apply_id
            and rp.get('baseline_eval_id') == payload.get('baseline_eval_id')
            and rp.get('dataset_id') == payload.get('dataset_id')
            and (rp.get('eval_options') or {}) == (payload.get('eval_options') or {})
        ):
            raise ValueError('matching abtest is already running')


def _apply_row_ready(row: dict[str, Any]) -> bool:
    result = (row.get('payload') or {}).get('result') or {}
    if row.get('status') not in {'succeeded', 'accepted'}:
        return False
    return result.get('status') == 'SUCCEEDED' and bool(
        row.get('final_commit') or result.get('final_commit'))


def _heuristic_plan(message: str, ctx: PlanContext) -> dict[str, Any] | None:
    text = message.lower()
    state = ctx.thread_state or {}
    latest = state.get('latest_tasks') or {}
    active = state.get('active_tasks') or []

    flow = _flow_from_text(message)
    if any(k in message for k in ('拒绝修改', '拒绝代码', '不接受修改', 'reject apply', 'reject code')):
        task_id = _latest_task_id(latest, 'apply')
        if task_id:
            return {
                'ops': [{'op': 'apply.reject',
                         'reason': '拒绝最近一次代码修改结果',
                         'args': {'task_id': task_id}}],
                'reply': '我会拒绝最近一次代码修改结果。',
            }
    if any(k in message for k in ('接受修改', '接受代码', '确认修改', '同意修改', 'accept apply', 'accept code')):
        task_id = _latest_task_id(latest, 'apply')
        if task_id:
            return {
                'ops': [{'op': 'apply.accept',
                         'reason': '接受最近一次代码修改结果',
                         'args': {'task_id': task_id}}],
                'reply': '我会接受最近一次代码修改结果。',
            }

    if _wants_cancel_restart(message):
        ops = _cancel_restart_ops(flow, latest, active)
        if ops:
            return {
                'ops': ops,
                'reply': '我会先取消当前相关任务，然后按原参数重新开始。',
            }

    if any(k in message for k in ('重试', '续跑', '继续执行', '继续跑', 'retry')):
        return {'ops': [{'op': 'task.continue_latest',
                         'reason': '续跑最近暂停或瞬时失败的任务',
                         'args': ({'flow': flow} if flow else {})}],
                'reply': '我会续跑最近暂停或瞬时失败的任务。'}
    if any(k in message for k in ('暂停', '停止', '打断', 'stop')):
        return {'ops': [{'op': 'task.stop_active',
                         'reason': '暂停当前活跃任务',
                         'args': ({'flow': flow} if flow else {})}],
                'reply': '我会暂停当前活跃任务。'}

    if flow == 'eval':
        dataset_id = _extract_id_after(message, ('数据集', '评测集', 'dataset'))
        if dataset_id:
            return {
                'ops': [{'op': 'eval.run',
                         'reason': f'用户请求对数据集 {dataset_id} 发起评测',
                         'args': {'dataset_id': dataset_id}}],
                'reply': f'已对数据集 {dataset_id} 发起评测任务。',
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
                'ops': [{'op': 'abtest.create',
                         'reason': '按显式参数创建 ABTest',
                         'args': args}],
                'reply': '我会按给定参数创建 ABTest。',
            }

    if ('数据集' in message or '评测集' in message) and any(k in message for k in ('重新生成', '重生成', '再生成', '生成有问题', '有问题')):
        ds = latest.get('dataset_gen') or {}
        payload = ds.get('payload') or {}
        args = {
            'kb_id': payload.get('kb_id') or _latest_artifact(state, 'kb_id'),
            'algo_id': payload.get('algo_id') or 'general_algo',
            'eval_name': _regen_name(payload.get('eval_name') or _latest_artifact(state, 'dataset_ids') or 'regen_eval'),
        }
        if payload.get('num_cases'):
            args['num_cases'] = payload['num_cases']
        if not args['kb_id']:
            return None
        ops: list[dict[str, Any]] = []
        if _has_active_flow(active, 'run'):
            ops.append({'op': 'task.stop_active',
                        'reason': '先暂停当前分析，避免继续基于错误数据集诊断',
                        'args': {'flow': 'run'}})
        ops.append({'op': 'dataset_gen.start',
                    'reason': '重新生成评测集',
                    'args': args})
        return {'ops': ops, 'reply': '我会先暂停当前分析，然后重新生成评测集。'}

    return None


def _flow_from_text(message: str) -> str | None:
    if any(k in message for k in ('abtest', 'ab test', '对比')):
        return 'abtest'
    if any(k in message for k in ('分析', '诊断', 'run')):
        return 'run'
    if (('评测' in message and '评测集' not in message)
            or any(k in message for k in ('跑评测', '发起评测', 'eval'))):
        return 'eval'
    if any(k in message for k in ('评测集', '数据集', 'dataset')):
        return 'dataset_gen'
    if any(k in message for k in ('修改', 'apply')):
        return 'apply'
    return None


def _has_active_flow(active: list[dict[str, Any]], flow: str) -> bool:
    return any(t.get('flow') == flow and t.get('status') == 'running' for t in active)


def _latest_artifact(state: dict[str, Any], key: str) -> str | None:
    vals = (state.get('artifacts') or {}).get(key) or []
    return vals[-1] if vals else None


def _latest_task_id(latest: dict[str, Any], flow: str) -> str | None:
    row = latest.get(flow) or {}
    return row.get('id')


def _wants_cancel_restart(message: str) -> bool:
    return any(k in message for k in ('取消后重新', '取消后重启', '取消并重新', '取消再重新', 'cancel and restart', '重新开始'))


def _extract_id_after(message: str, markers: tuple[str, ...]) -> str | None:
    for marker in markers:
        m = re.search(re.escape(marker) + r'\s*([A-Za-z0-9_.:-]+)', message, re.I)
        if m:
            return m.group(1).strip('，。,. ')
    return None


def _extract_named_id(message: str, name: str) -> str | None:
    pattern = rf'{re.escape(name)}\s*[:=：]?\s*([A-Za-z0-9_.:/-]+)'
    m = re.search(pattern, message, re.I)
    return m.group(1).strip('，。,. ') if m else None


def _cancel_restart_ops(flow: str | None, latest: dict[str, Any],
                        active: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not flow:
        return []
    ops: list[dict[str, Any]] = []
    if _has_active_flow(active, flow):
        ops.append({'op': 'task.cancel_active',
                    'reason': f'取消当前 {flow} 任务',
                    'args': {'flow': flow}})
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
        return {'op': 'eval.run' if args.get('dataset_id') else 'eval.fetch',
                'reason': '重新执行评测任务',
                'args': {k: v for k, v in args.items() if v}} if (args.get('dataset_id') or args.get('eval_id')) else None
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
    base = re.sub(r'[^A-Za-z0-9_.-]+', '_', name).strip('_') or 'regen_eval'
    return f'{base}_regen_{time.strftime("%H%M%S")}'
