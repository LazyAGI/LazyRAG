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
        if ctx.thread_state_summary:
            artifact_hint = (
                f"\n\nCurrent thread artifacts:\n{ctx.thread_state_summary}\n\n"
                f"When user refers to '刚才的/最新的/上一个', use these artifact IDs."
            )
        parsed = _heuristic_plan(message, ctx)
        if parsed is None:
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
            f"- '修改代码/apply' -> apply.start with report_id\n"
            f"- 'ABTest/对比' -> abtest.create with apply_id, baseline_eval_id, dataset_id\n"
            f"- Extract specific IDs from artifacts when user refers to them\n"
            f"- '接受修改并合并' -> apply.accept with task_id and auto_next='merge'\n"
            f"- '接受修改、合并并部署' -> apply.accept with task_id and auto_next='merge_deploy'\n"
            f"- '合并' -> merge.start with apply_id\n"
            f"- '部署' -> deploy.start with merge_id\n"
            f"Reply in strict JSON only: "
            f"{{\"ops\":[{{\"op\":\"...\",\"reason\":\"...\",\"args\":{{...}}}}],\"reply\":\"...\"}}"
            )
            try:
                raw = self.llm(prompt)
                parsed = _parse_json_object(raw)
            except Exception:
                parsed = {'ops': [], 'reply': f'收到：{message}。暂无可自动执行的操作。'}

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

        requires_confirm = any(p.safety in {'destructive', 'long_running'} for p in previews)
        reply = parsed.get('reply', f'收到：{message}。')
        if requires_confirm:
            reply += ' 其中包含需要确认的操作，请确认后执行。'
        elif previews:
            reply += ' 所有操作均为安全操作，可直接执行。'

        return Intent(
            intent_id=f'intent_{ctx.thread_id}_{uuid.uuid4().hex[:8]}',
            thread_id=ctx.thread_id,
            user_message=message,
            reply=reply,
            suggested_ops_preview=previews,
            requires_confirm=requires_confirm,
            thinking=parsed.get('thinking', ''),
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
        for op_data in raw_ops:
            try:
                op_name = op_data['op']
                args = op_data.get('args', {})
                caps.validate(op_name, args)
                _validate_schema(op_name, args, ctx)
                ops.append({'op': op_name, 'args': args})
            except (KeyError, TypeError, ValueError) as exc:
                warnings.append(f"validation failed: {exc}")
        return PlanResult(
            intent_id=intent.intent_id,
            ops=ops,
            warnings=warnings,
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
        'merge.start': schemas.MergeCreate,
        'deploy.start': schemas.DeployCreate,
        'abtest.create': schemas.AbtestCreate,
    }
    model = model_by_op.get(op)
    if model is None:
        return
    payload = dict(args)
    if 'thread_id' not in payload:
        payload['thread_id'] = ctx.thread_id
    model(**payload)


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


def _heuristic_plan(message: str, ctx: PlanContext) -> dict[str, Any] | None:
    text = message.lower()
    state = ctx.thread_state or {}
    latest = state.get('latest_tasks') or {}
    active = state.get('active_tasks') or []
    checkpoints = state.get('pending_checkpoints') or []

    flow = _flow_from_text(message)
    if checkpoints and any(k in message for k in ('拒绝检查点', '取消检查点', '终止检查点', 'checkpoint cancel', 'checkpoint reject')):
        cp_id = checkpoints[0].get('id')
        return {
            'ops': [{'op': 'checkpoint.respond',
                     'reason': '取消当前 checkpoint，暂停后续分析',
                     'args': {'cp_id': cp_id, 'choice': 'cancel'}}],
            'reply': '我会拒绝当前检查点并暂停后续分析。',
        }
    if checkpoints and any(k in message for k in ('修改检查点', '调整检查点', 'revise checkpoint', '重新规划检查点')):
        cp_id = checkpoints[0].get('id')
        return {
            'ops': [{'op': 'checkpoint.respond',
                     'reason': '提交 checkpoint 修改意见并继续',
                     'args': {'cp_id': cp_id, 'choice': 'revise', 'feedback': message}}],
            'reply': '我会把你的修改意见写入检查点并继续执行。',
        }
    if checkpoints and ('checkpoint' in text or '检查点' in text or '批准' in text):
        cp_id = checkpoints[0].get('id')
        return {
            'ops': [{'op': 'checkpoint.respond',
                     'reason': '批准当前待处理 checkpoint 并继续任务',
                     'args': {'cp_id': cp_id, 'choice': 'approve'}}],
            'reply': '我会批准当前检查点并继续执行。',
        }

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
            auto_next = 'merge' if any(k in message for k in ('合并', 'merge')) else 'none'
            return {
                'ops': [{'op': 'apply.accept',
                         'reason': '接受最近一次代码修改结果',
                         'args': {'task_id': task_id, 'auto_next': auto_next}}],
                'reply': '我会接受最近一次代码修改结果。' + ('随后启动合并。' if auto_next == 'merge' else ''),
            }

    if any(k in message for k in ('拒绝合并', '取消合并', '不要合并', 'reject merge')):
        task_id = _latest_task_id(latest, 'merge')
        if task_id:
            return {
                'ops': [{'op': 'merge.cancel',
                         'reason': '取消最近一次合并任务',
                         'args': {'task_id': task_id}}],
                'reply': '我会取消最近一次合并任务。',
            }
    if any(k in message for k in ('接受合并', '确认合并', '同意合并', '开始合并', 'accept merge')):
        apply_id = _latest_task_id(latest, 'apply')
        if apply_id:
            return {
                'ops': [{'op': 'merge.start',
                         'reason': '基于最近一次已接受的代码修改启动合并',
                         'args': {'apply_id': apply_id}}],
                'reply': '我会基于最近一次代码修改启动合并。',
            }

    if any(k in message for k in ('拒绝部署', '取消部署', '不要部署', 'reject deploy')):
        task_id = _latest_task_id(latest, 'deploy')
        if task_id:
            return {
                'ops': [{'op': 'deploy.cancel',
                         'reason': '取消最近一次部署任务',
                         'args': {'task_id': task_id}}],
                'reply': '我会取消最近一次部署任务。',
            }
    if any(k in message for k in ('接受部署', '确认部署', '同意部署', '开始部署', 'accept deploy')):
        merge_id = _latest_task_id(latest, 'merge')
        if merge_id:
            return {
                'ops': [{'op': 'deploy.start',
                         'reason': '基于最近一次合并结果启动部署',
                         'args': {'merge_id': merge_id}}],
                'reply': '我会基于最近一次合并结果启动部署。',
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

    if ('数据集' in message or '评测集' in message) and any(k in message for k in ('重新生成', '重生成', '再生成', '生成有问题', '有问题')):
        ds = latest.get('dataset_gen') or {}
        payload = ds.get('payload') or {}
        args = {
            'kb_id': payload.get('kb_id') or _latest_artifact(state, 'kb_id'),
            'algo_id': payload.get('algo_id') or 'general_algo',
            'eval_name': _regen_name(payload.get('eval_name') or _latest_artifact(state, 'dataset_ids') or 'regen_eval'),
        }
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
    if any(k in message for k in ('分析', '诊断', 'run')):
        return 'run'
    if any(k in message for k in ('评测集', '数据集', 'dataset')):
        return 'dataset_gen'
    if any(k in message for k in ('评测', 'eval')):
        return 'eval'
    if any(k in message for k in ('修改', 'apply')):
        return 'apply'
    if any(k in message for k in ('abtest', 'ab test', '对比')):
        return 'abtest'
    if any(k in message for k in ('合并', 'merge')):
        return 'merge'
    if any(k in message for k in ('部署', 'deploy')):
        return 'deploy'
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


def _cancel_restart_ops(flow: str | None, latest: dict[str, Any],
                        active: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not flow:
        return []
    ops: list[dict[str, Any]] = []
    if _has_active_flow(active, flow) or _latest_task_id(latest, flow):
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
    if flow == 'merge':
        return {'op': 'merge.start', 'reason': '重新启动合并任务', 'args': payload} if payload.get('apply_id') else None
    if flow == 'deploy':
        return {'op': 'deploy.start', 'reason': '重新启动部署任务', 'args': payload} if payload.get('merge_id') else None
    return None


def _regen_name(name: str) -> str:
    base = re.sub(r'[^A-Za-z0-9_.-]+', '_', name).strip('_') or 'regen_eval'
    return f'{base}_regen_{time.strftime("%H%M%S")}'
