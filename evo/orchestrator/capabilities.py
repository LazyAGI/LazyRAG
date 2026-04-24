from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Capability:
    op: str
    flow: str
    description: str
    params_schema: dict[str, Any] = field(default_factory=dict)
    blocking: bool = False
    idempotent: bool = False


def _required(*names: str) -> dict:
    return {'required': list(names)}


REGISTRY: dict[str, Capability] = {}


def _add(cap: Capability) -> None:
    REGISTRY[cap.op] = cap


_add(Capability('run.start', 'run', '启动一次诊断分析',
                params_schema={'optional': ['extra_context', 'eval_id',
                                              'badcase_limit', 'score_field']},
                blocking=True))
_add(Capability('run.stop', 'run', '请求暂停当前分析',
                params_schema=_required('task_id'), idempotent=True))
_add(Capability('run.continue', 'run', '继续上次暂停的分析',
                params_schema=_required('task_id'), blocking=True))
_add(Capability('run.cancel', 'run', '彻底取消分析任务',
                params_schema=_required('task_id'), idempotent=True))

_add(Capability('apply.start', 'apply', '基于报告启动代码修改',
                params_schema={'optional': ['report_id', 'extra_instructions']},
                blocking=True))
_add(Capability('apply.stop', 'apply', '暂停 apply',
                params_schema=_required('task_id'), idempotent=True))
_add(Capability('apply.continue', 'apply', '继续 apply',
                params_schema=_required('task_id'), blocking=True))
_add(Capability('apply.cancel', 'apply', '取消 apply',
                params_schema=_required('task_id'), idempotent=True))
_add(Capability('apply.accept', 'apply', '接受 apply 结果',
                params_schema=_required('task_id'), idempotent=True))
_add(Capability('apply.reject', 'apply', '拒绝 apply 结果',
                params_schema=_required('task_id'), idempotent=True))

_add(Capability('eval.fetch', 'eval', '拉取已存在的评测报告与全部 trace',
                params_schema=_required('eval_id'), blocking=True))
_add(Capability('eval.run', 'eval', '在指定数据集上跑一次评测并拉 trace',
                params_schema=_required('dataset_id'), blocking=True))
_add(Capability('eval.cancel', 'eval', '取消评测任务',
                params_schema=_required('task_id'), idempotent=True))

_add(Capability('abtest.create', 'abtest', '基于 apply 起 abtest 并比对',
                params_schema=_required('apply_id', 'baseline_eval_id', 'dataset_id'),
                blocking=True))
_add(Capability('abtest.stop', 'abtest', '暂停 abtest',
                params_schema=_required('task_id'), idempotent=True))
_add(Capability('abtest.continue', 'abtest', '续跑 abtest',
                params_schema=_required('task_id'), blocking=True))
_add(Capability('abtest.cancel', 'abtest', '取消 abtest',
                params_schema=_required('task_id'), idempotent=True))

_add(Capability('chat.list', 'chat', '列出已注册的 chat 实例'))
_add(Capability('chat.stop', 'chat', '停止指定 chat 进程',
                params_schema=_required('chat_id'), idempotent=True))
_add(Capability('chat.promote', 'chat', '将 chat 升级为生产',
                params_schema=_required('chat_id'), idempotent=True))
_add(Capability('chat.demote', 'chat', '将 chat 降级为候选',
                params_schema=_required('chat_id'), idempotent=True))
_add(Capability('chat.retire', 'chat', '回收 chat 实例',
                params_schema=_required('chat_id'), idempotent=True))

_add(Capability('checkpoint.respond', 'checkpoint',
                '响应 indexer 等步骤的检查点',
                params_schema=_required('cp_id', 'choice'), idempotent=True))
_add(Capability('checkpoint.list_pending', 'checkpoint',
                '列出当前 thread 的待响应 checkpoint'))

_add(Capability('query.list_threads', 'query', '列出 thread'))
_add(Capability('query.get_report', 'query', '查看分析报告',
                params_schema=_required('report_id')))
_add(Capability('query.list_evals', 'query', '列出已挂的评测'))
_add(Capability('query.list_chats', 'query', '列出 chat 池'))


def get(op: str) -> Capability:
    if op not in REGISTRY:
        raise KeyError(f'unknown op {op!r}')
    return REGISTRY[op]


def all_ops() -> list[str]:
    return list(REGISTRY)


def render_for_prompt() -> str:
    lines: list[str] = ['# Capabilities (op | flow | description)']
    for op in sorted(REGISTRY):
        cap = REGISTRY[op]
        lines.append(f'- `{op}` | {cap.flow} | {cap.description}')
    return '\n'.join(lines)


def validate(op: str, args: dict[str, Any]) -> None:
    cap = get(op)
    required = cap.params_schema.get('required') or []
    missing = [k for k in required if k not in args]
    if missing:
        raise ValueError(f'op {op}: missing required args {missing}')
