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
    safety: str = 'safe'


def _required(*names: str) -> dict:
    return {'required': list(names)}


REGISTRY: dict[str, Capability] = {}


def _add(cap: Capability) -> None:
    REGISTRY[cap.op] = cap


_add(Capability('run.start', 'run', '启动一次诊断分析',
                params_schema={'optional': ['extra_context', 'eval_id',
                                              'badcase_limit', 'score_field']},
                blocking=True, safety='long_running'))
_add(Capability('run.stop', 'run', '请求暂停当前分析',
                params_schema=_required('task_id'), idempotent=True, safety='destructive'))
_add(Capability('run.continue', 'run', '继续上次暂停的分析',
                params_schema=_required('task_id'), blocking=True, safety='long_running'))
_add(Capability('run.cancel', 'run', '彻底取消分析任务',
                params_schema=_required('task_id'), idempotent=True, safety='destructive'))

_add(Capability('task.stop_active', 'task', '暂停当前 thread 中指定 flow 的活跃任务',
                params_schema={'optional': ['flow']}, idempotent=True, safety='destructive'))
_add(Capability('task.cancel_active', 'task', '取消当前 thread 中指定 flow 的活跃任务',
                params_schema={'optional': ['flow']}, idempotent=True, safety='destructive'))
_add(Capability('task.continue_latest', 'task', '续跑当前 thread 中最近的暂停或瞬时失败任务',
                params_schema={'optional': ['flow', 'task_id']}, blocking=True, safety='long_running'))

_add(Capability('apply.start', 'apply', '基于报告启动代码修改',
                params_schema={'optional': ['report_id', 'extra_instructions']},
                blocking=True, safety='long_running'))
_add(Capability('apply.stop', 'apply', '暂停 apply',
                params_schema=_required('task_id'), idempotent=True, safety='destructive'))
_add(Capability('apply.continue', 'apply', '继续上次暂停的 apply',
                params_schema=_required('task_id'), blocking=True, safety='long_running'))
_add(Capability('apply.cancel', 'apply', '取消 apply',
                params_schema=_required('task_id'), idempotent=True, safety='destructive'))
_add(Capability('apply.accept', 'apply', '接受 apply 结果（可继续合并/部署）',
                params_schema={'required': ['task_id'],
                               'optional': ['auto_next']},
                idempotent=True, safety='destructive'))
_add(Capability('apply.reject', 'apply', '拒绝 apply 结果',
                params_schema=_required('task_id'), idempotent=True, safety='destructive'))

_add(Capability('eval.fetch', 'eval', '拉取已存在的评测报告与全部 trace',
                params_schema=_required('eval_id'), blocking=True, safety='safe'))
_add(Capability('eval.run', 'eval', '在指定数据集上跑一次评测并拉 trace',
                params_schema={'required': ['dataset_id'],
                               'optional': ['target_chat_url', 'options']},
                blocking=True, safety='long_running'))
_add(Capability('eval.cancel', 'eval', '取消评测任务',
                params_schema=_required('task_id'), idempotent=True, safety='destructive'))

_add(Capability('abtest.create', 'abtest', '基于 apply 起 abtest 并比对',
                params_schema={'required': ['apply_id', 'baseline_eval_id', 'dataset_id'],
                               'optional': ['candidate_chat_id', 'target_chat_url',
                                            'eval_options', 'policy']},
                blocking=True, safety='long_running'))
_add(Capability('abtest.stop', 'abtest', '暂停 abtest',
                params_schema=_required('task_id'), idempotent=True, safety='destructive'))
_add(Capability('abtest.continue', 'abtest', '续跑 abtest',
                params_schema=_required('task_id'), blocking=True, safety='long_running'))
_add(Capability('abtest.cancel', 'abtest', '取消 abtest',
                params_schema=_required('task_id'), idempotent=True, safety='destructive'))

_add(Capability('dataset_gen.start', 'dataset_gen', '从知识库生成评测集',
                params_schema={'optional': ['kb_id', 'algo_id', 'eval_name', 'num_cases']},
                blocking=True, safety='long_running'))
_add(Capability('dataset_gen.cancel', 'dataset_gen', '取消生成任务',
                params_schema=_required('task_id'), idempotent=True, safety='destructive'))

_add(Capability('query.list_threads', 'query', '列出 thread', safety='safe'))
_add(Capability('query.get_report', 'query', '查看分析报告',
                params_schema=_required('report_id'), safety='safe'))
_add(Capability('query.list_evals', 'query', '列出已挂的评测', safety='safe'))
_add(Capability('query.list_chats', 'query', '列出 chat 池', safety='safe'))


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
