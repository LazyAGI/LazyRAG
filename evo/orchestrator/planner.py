from __future__ import annotations

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
        prompt = (
            f"User message: {message}{artifact_hint}\n\n"
            f"Available operations:\n{cap_summary}\n\n"
            f"You are a task planner. Map the user's natural language request to operations.\n"
            f"Rules:\n"
            f"- '创建评测集/生成数据集' -> dataset_gen.start with kb_id, eval_name\n"
            f"- '评测/跑评测/生成报告' -> eval.run with dataset_id, target_chat_url\n"
            f"- '分析/诊断' -> run.start with eval_id\n"
            f"- '修改代码/apply' -> apply.start with report_id\n"
            f"- 'ABTest/对比' -> abtest.create with apply_id, baseline_eval_id, dataset_id\n"
            f"- Extract specific IDs from artifacts when user refers to them\n"
            f"- '接受修改并合并' -> apply.accept with task_id and auto_next='merge'\n"
            f"- '接受修改、合并并部署' -> apply.accept with task_id and auto_next='merge_deploy'\n"
            f"- '合并' -> merge.start with apply_id\n"
            f"- '部署' -> deploy.start with merge_id\n"
            f"Reply in JSON: {{'ops': [{{'op': '...', 'reason': '...', 'args': {{...}}}}], 'reply': '...'}}"
        )
        try:
            raw = self.llm(prompt)
            if isinstance(raw, list):
                raw = raw[-1] if raw else '{}'
            parsed = __import__('json').loads(raw) if isinstance(raw, str) else dict(raw)
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
            raw_ops = self._materialize_with_llm(intent, ctx)
        if not raw_ops:
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
            f"{{\"ops\":[{{\"op\":\"eval.run\",\"args\":{{\"dataset_id\":\"...\"}}}}]}}"
        )
        try:
            raw = self.llm(prompt)
            if isinstance(raw, list):
                raw = raw[-1] if raw else '{}'
            parsed = __import__('json').loads(raw) if isinstance(raw, str) else dict(raw)
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
