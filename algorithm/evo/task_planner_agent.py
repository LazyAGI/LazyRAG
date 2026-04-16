"""Convert badcase analysis reports into executable task plans.

The planner is deterministic on purpose: analysis reports already contain the
hypotheses, evidence and validation signals. This module normalizes those
signals into small TaskPlan objects that can be handed to opencode or another
code-changing agent.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, NamedTuple, Optional, Sequence, Tuple
try:
    import lazyllm
    from lazyllm.components.formatter import JsonFormatter
    from lazyllm import ModuleBase
except Exception:  # pragma: no cover - LazyLLM is optional for deterministic planning.
    lazyllm = None
    JsonFormatter = None
    ModuleBase = object



# ---------------------------------------------------------------------------
# TaskPlan dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TaskPlan:
    task_id: str
    report_id: str
    module: str
    change_type: str
    goal: str
    plan: List[str]
    risk: int
    priority: int = 0
    # --- new fields that help downstream agents ---
    trigger_cases: List[str] = field(default_factory=list)
    trigger_metric: str = ''
    confidence: float = 0.0
    cascade_type: str = ''
    bottleneck_stage: str = ''
    # --- existing enrichment fields ---
    evidence: List[str] = field(default_factory=list)
    change_targets: List[Dict[str, Any]] = field(default_factory=list)
    report_context: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# LazyLLM module wrapper
# ---------------------------------------------------------------------------

class TaskPlannerAgent(ModuleBase):
    """LazyLLM module wrapper for the deterministic report-to-plan planner."""

    def __init__(
        self,
        code_root: str | Path = '.',
        output_format: str = 'task_plans',
        *,
        use_model_plan: bool = False,
        return_trace: bool = False,
    ) -> None:
        if lazyllm is not None:
            super().__init__(return_trace=return_trace)
        self.code_root = Path(code_root)
        self.output_format = output_format
        self.use_model_plan = use_model_plan

    def forward(self, report: Any = None, code_root: str | Path | None = None,
                output_format: str | None = None, **kwargs: Any) -> Any:
        report_data, resolved_root, resolved_fmt, review_result, validation_result = _normalize_agent_input(
            report=report,
            code_root=code_root or self.code_root,
            output_format=output_format or self.output_format,
            kwargs=kwargs,
        )
        plan_model_role = str(kwargs.get('plan_model_role') or 'llm_instruct')
        use_model_plan = bool(kwargs.get('use_model_plan', self.use_model_plan))
        tasks = build_task_plans(
            report_data, resolved_root,
            plan_model_role=plan_model_role,
            use_model_plan=use_model_plan,
            review_result=review_result,
            validation_result=validation_result,
        )
        schema = str(kwargs.get('schema') or kwargs.get('output_schema') or 'full')
        formatted = _format_task_output(
            tasks,
            report_data,
            resolved_fmt,
            schema=schema,
        )
        output_path = kwargs.get('output_path') or kwargs.get('output')
        if output_path or bool(kwargs.get('save')):
            _write_output(formatted, output_path or _default_plan_output_path_for_report(report_data))
        return formatted


# ---------------------------------------------------------------------------
# Module aliases and file hints
# ---------------------------------------------------------------------------

_MODULE_ALIASES = {
    'chunk': 'chunker', 'chunking': 'chunker', 'chunker': 'chunker', 'split': 'chunker',
    'retrieve': 'retriever', 'retrieval': 'retriever', 'retriever': 'retriever',
    'rerank': 'retriever', 'reranker': 'retriever',
    'query_rewrite': 'query_rewriter', 'query-rewrite': 'query_rewriter',
    'rewrite': 'query_rewriter', 'rewriter': 'query_rewriter',
    'generate': 'generator', 'generation': 'generator', 'generator': 'generator', 'llm': 'generator',
}

_MODULE_METADATA: Dict[str, Dict[str, Any]] = {
    'chunker': {
        'files': [
            'algorithm/parsing/build_document.py',
            'algorithm/parsing/transform/para_parser.py',
            'algorithm/parsing/transform/general_parser.py',
        ],
        'keywords': ('chunk', 'split', 'overlap', 'ParagraphSplitter', 'LineSplitter', 'GeneralParser'),
    },
    'retriever': {
        'files': [
            'algorithm/chat/pipelines/builders/get_ppl_search.py',
            'algorithm/chat/pipelines/builders/get_retriever.py',
            'algorithm/chat/utils/load_config.py',
        ],
        'keywords': ('retriever', 'retrieval', 'Reranker', 'topk', 'RRFFusion', 'AdaptiveK', 'similarity'),
    },
    'query_rewriter': {
        'files': [
            'algorithm/chat/components/process/multiturn_query_rewriter.py',
            'algorithm/chat/prompts/rewrite.py',
            'algorithm/chat/pipelines/naive.py',
        ],
        'keywords': ('rewrite', 'rewriter', 'rewritten_query', 'MULTITURN_QUERY_REWRITE_PROMPT'),
    },
    'generator': {
        'files': [
            'algorithm/chat/pipelines/builders/get_ppl_generate.py',
            'algorithm/chat/prompts/rag_answer.py',
            'algorithm/chat/prompts/agentic.py',
            'algorithm/chat/components/generate/output_parser.py',
        ],
        'keywords': ('generate', 'generator', 'faithfulness', 'hallucination', 'RAG_ANSWER', 'answer'),
    },
}
_PREFERRED_FILES: Dict[str, List[str]] = {
    module: list(meta['files']) for module, meta in _MODULE_METADATA.items()
}
_MODULE_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    module: tuple(meta['keywords']) for module, meta in _MODULE_METADATA.items()
}

_IGNORED_DIRS = {'.git', '.pytest_cache', '__pycache__', 'node_modules', 'dist', 'build', 'output', 'public', 'generated'}
_CODE_EXTENSIONS = {'.py', '.go', '.ts', '.tsx', '.js', '.jsx', '.yaml', '.yml'}
_DEFAULT_CODE_ROOT = Path(__file__).resolve().parents[2]
_PLAN_OUTPUT_DIR = _DEFAULT_CODE_ROOT / 'algorithm' / 'evo' / 'output' / 'plan'
_GOAL_TEXT_LIMIT = 120
_INLINE_TEXT_LIMIT = 180
_KEY_EVIDENCE_LIMIT = 360
_EVIDENCE_TEXT_LIMIT = 520
_MAX_PLAN_STEPS = 8

_STEPS_TEMPLATE: Dict[str, List[str]] = {
    'retriever': [
        '定位检索链路和召回配置：{files}',
        '核对零召回证据：{evidence}',
        '重点检查可调目标：{params}',
        '围绕触发案例记录 query、召回 chunk、关键短语命中和 doc_recall/context_recall',
        '以配置化或最小逻辑改动提升相关文档召回，保留可回滚参数',
    ],
    'query_rewriter': [
        '定位 query rewrite 链路和提示词：{files}',
        '核对改写失败证据：{evidence}',
        '将陈述式/学术断言查询压缩为包含核心概念的检索意图',
        '增加或调整长查询意图抽取、关键词保留和去冗余规则',
        '验证改写后 query 不引入新实体且能提升召回入口质量',
    ],
    'chunker': [
        '定位切分链路和 chunk 参数：{files}',
        '核对跨段落证据：{evidence}',
        '检查 chunk_size、chunk_overlap、段落合并和父子节点策略是否造成关键语义被拆散',
        '调整 overlap 或相邻段落聚合策略，让跨段 Ground Truth 能以可检索上下文保留',
        '验证 chunk 变长没有显著引入无关上下文或拖慢检索',
    ],
    'generator': [
        '定位生成链路和回答约束：{files}',
        '核对幻觉证据：{evidence}',
        '检查无相关上下文时是否仍强制生成确定性答案',
        '增加 insufficient-context fallback 或证据引用约束，避免编造具体机构、面积、数据',
        '验证 faithfulness 提升且 answer_correctness 不因过度拒答而退化',
    ],
}

_EVIDENCE_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    'retriever': ('context_recall', 'doc_recall', '关键短语', 'retrieved', '零召回'),
    'chunker': ('GT spans', 'Ground Truth', '文本段', 'chunk', '切块'),
    'query_rewriter': ('rewrite', 'compression', '查询', '意图', '62'),
    'generator': ('faithfulness', 'hallucination', '幻觉', '无相关上下文'),
}

# Opencode execution constraints (embedded in output JSON)
_OPENCODE_CONSTRAINTS = [
    '只修改当前任务需要的代码，不回退无关变更。',
    '每个任务完成后运行对应 validation 步骤或说明无法运行的原因。',
    '若多个任务影响同一模块，先完成最高 risk 的任务，并复用已完成改动。',
    '输出改动文件、验证结果和剩余风险。',
]

_MODULE_DEPENDENCIES: Dict[str, List[str]] = {
    'generator': ['retriever'],
    'retriever': [],
    'query_rewriter': [],
    'chunker': [],
}

_DEFAULT_ORDER: Dict[str, int] = {
    'retriever': 0, 'query_rewriter': 1, 'chunker': 2, 'generator': 3, 'unknown': 9,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_report(report_path: str | Path) -> Dict[str, Any]:
    path = Path(report_path)
    with path.open('r', encoding='utf-8') as f:
        report = json.load(f)
    if not isinstance(report, dict):
        raise ValueError(f'Report `{path}` must be a JSON object.')
    return report


def build_task_plans(
    report: Mapping[str, Any],
    code_root: str | Path,
    *,
    plan_model_role: str = 'llm_instruct',
    use_model_plan: bool = False,
    review_result: Optional[Mapping[str, Any]] = None,
    validation_result: Optional[Mapping[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Build normalized TaskPlan dicts from an analysis report."""
    root = Path(code_root).resolve()
    review_feedback = _extract_feedback_mapping(
        explicit=review_result,
        report=report,
        keys=('review_result', 'code_review_result', 'code_review', 'review'),
    )
    validation_feedback = _extract_feedback_mapping(
        explicit=validation_result,
        report=report,
        keys=('validation_result', 'test_validation_result', 'test_result', 'test_validation'),
    )
    resolved_plan_model = None
    if use_model_plan:
        _trace_model_plan(f'enabled; resolving model role `{plan_model_role}`')
        resolved_plan_model = _resolve_plan_model(plan_model_role)
        if resolved_plan_model is None:
            _trace_model_plan('model resolution failed; using deterministic fallback steps')
        else:
            _trace_model_plan(f'resolved model: {type(resolved_plan_model).__name__}')

    report_id = _report_id(report)
    feedback_tasks = _build_feedback_tasks(
        report, root,
        report_id=report_id,
        review_result=review_feedback,
        validation_result=validation_feedback,
        plan_model=resolved_plan_model,
    )
    if feedback_tasks is not None:
        return [asdict(task) for task in feedback_tasks]

    action_list = report.get('action_list') or {}
    if not isinstance(action_list, Mapping):
        raise ValueError('Report field `action_list` must be an object.')

    modification_plans = report.get('modification_plan') or []
    if not isinstance(modification_plans, list):
        modification_plans = []

    tasks = _build_task_plans_from_actions(
        report, root, modification_plans, plan_model=resolved_plan_model,
    )
    if not tasks:
        tasks = _build_fallback_tasks(root, modification_plans, report_id=report_id, plan_model=resolved_plan_model)
    return [asdict(task) for task in tasks]





def build_lazyllm_task_planner(
    code_root: str | Path = '.',
    output_format: str = 'task_plans',
) -> Any:
    """Build a LazyLLM pipeline containing the TaskPlannerAgent."""
    if lazyllm is None:
        raise RuntimeError('LazyLLM is required to build a task planner pipeline.')
    with lazyllm.pipeline() as ppl:
        ppl.planner = TaskPlannerAgent(code_root=code_root, output_format=output_format)
    return ppl


# ---------------------------------------------------------------------------
# Core plan building
# ---------------------------------------------------------------------------

class _Record(NamedTuple):
    action_key: str
    action: Mapping[str, Any]
    finding: Mapping[str, Any]
    mod_plan: Mapping[str, Any]


def _build_task_plans_from_actions(
    report: Mapping[str, Any],
    root: Path,
    modification_plans: Sequence[Any],
    *,
    plan_model: Any = None,
) -> List[TaskPlan]:
    action_list = report.get('action_list') or {}
    if not isinstance(action_list, Mapping) or not action_list:
        return []

    grouped: Dict[str, List[_Record]] = {}
    for action_key, raw_action in _sorted_actions(action_list):
        if not isinstance(raw_action, Mapping):
            continue
        finding = _matching_finding(report, action_key, raw_action)
        explicit_changes = _explicit_change_records(raw_action)
        if explicit_changes:
            for module, change_plan in explicit_changes:
                grouped.setdefault(module, []).append(_Record(action_key, raw_action, finding, change_plan))
            continue
        mod_plan = _matching_modification_plan(raw_action, finding, modification_plans)
        module = _infer_module(raw_action, finding, mod_plan)
        grouped.setdefault(module, []).append(_Record(action_key, raw_action, finding, mod_plan))

    if not grouped:
        return []

    module_order = _rank_modules(report, grouped)
    tid_map = {mod: f'T{i + 1:03d}' for i, mod in enumerate(module_order)}
    tasks: List[TaskPlan] = []
    for priority, module in enumerate(module_order, start=1):
        task = _build_module_task(
            report, root, module, grouped[module],
            task_id=tid_map[module], priority=priority,
            tid_map=tid_map,
        )
        tasks.append(task)
    return _apply_model_plan(plan_model, tasks)


def _apply_model_plan(plan_model: Any, tasks: Sequence[TaskPlan]) -> List[TaskPlan]:
    """Apply LLM-generated plan steps if model is available, otherwise return tasks as-is."""
    return _model_plan_steps_for_tasks(plan_model, tasks) if plan_model is not None else list(tasks)


def _explicit_change_records(action: Mapping[str, Any]) -> List[Tuple[str, Mapping[str, Any]]]:
    """Return explicit action.changes entries as module-scoped modification plans."""
    changes = action.get('changes')
    if not isinstance(changes, Mapping):
        return []

    records: List[Tuple[str, Mapping[str, Any]]] = []
    for raw_module, raw_change in changes.items():
        if not isinstance(raw_change, Mapping):
            continue
        module = _canonical_module(str(raw_module))
        if module == 'unknown':
            continue
        change_plan: Dict[str, Any] = dict(raw_change)
        change_plan.setdefault('stage', module)
        if raw_change.get('type') and not raw_change.get('change_type'):
            change_plan['change_type'] = raw_change.get('type')
        records.append((module, change_plan))
    return records


def _build_fallback_tasks(
    root: Path, modification_plans: Sequence[Any],
    *, report_id: str = 'unknown_report', plan_model: Any = None,
) -> List[TaskPlan]:
    tasks: List[TaskPlan] = []
    for index, mod_plan in enumerate(modification_plans, start=1):
        if not isinstance(mod_plan, Mapping):
            continue
        module = _canonical_module(str(mod_plan.get('stage') or 'unknown'))
        action: Dict[str, Any] = {
            'priority': mod_plan.get('priority'),
            'hypothesis': mod_plan.get('hypothesis'),
            'validation_cases': [],
        }
        records: List[_Record] = [_Record(f'modification_{index}', action, {}, mod_plan)]
        tid = f'T{len(tasks) + 1:03d}'
        tasks.append(_build_module_task(
            {'report_id': report_id}, root, module, records,
            task_id=tid, priority=len(tasks) + 1,
            tid_map={module: tid},
        ))
    return _apply_model_plan(plan_model, tasks)


def _build_feedback_tasks(
    report: Mapping[str, Any],
    root: Path,
    *,
    report_id: str,
    review_result: Mapping[str, Any],
    validation_result: Mapping[str, Any],
    plan_model: Any = None,
) -> Optional[List[TaskPlan]]:
    """Build next-round tasks from downstream review/test feedback.

    ``None`` means no feedback was supplied and the caller should keep the
    original report-driven planning path. In the outer evolution flow, any
    returned review or test result represents a failed gate, so every supplied
    feedback payload becomes a repair task.
    """
    has_review = bool(review_result)
    has_validation = bool(validation_result)
    if not has_review and not has_validation:
        return None

    review_gate = _review_gate_status(review_result) if has_review else {}
    validation_gate = _validation_gate_status(validation_result) if has_validation else {}
    target_files = _feedback_target_files(report, root)
    tasks: List[TaskPlan] = []
    if has_review:
        tasks.append(_build_review_feedback_task(
            report, root, review_result, review_gate, target_files,
            task_id=f'T{len(tasks) + 1:03d}', report_id=report_id,
        ))
    if has_validation:
        tasks.append(_build_validation_feedback_task(
            report, root, validation_result, validation_gate, target_files,
            task_id=f'T{len(tasks) + 1:03d}', report_id=report_id,
        ))
    if not tasks:
        return None

    return _apply_model_plan(plan_model, tasks)


def _build_review_feedback_task(
    report: Mapping[str, Any],
    root: Path,
    review_result: Mapping[str, Any],
    gate: Mapping[str, Any],
    target_files: Sequence[str],
    *,
    task_id: str,
    report_id: str,
) -> TaskPlan:
    failed = _to_str_list(gate.get('failed_gates'))
    description = str(review_result.get('description') or '').strip()
    suggestions = _to_str_list(review_result.get('suggestions'))[:6]
    side_effect_risk = _parse_int(review_result.get('side_effect_risk'))
    report_context = _build_feedback_report_context(report, root, review_result, feedback_kind='review')
    evidence = []
    if description:
        evidence.append(description)
    if failed:
        evidence.append(f'代码审查未通过：{", ".join(failed)}')
    if side_effect_risk is not None:
        evidence.append(f'side_effect_risk={side_effect_risk}')
    evidence.extend(suggestions)
    evidence.extend(_to_str_list(report_context.get('evidence'))[:4])

    files = '、'.join(target_files[:4]) if target_files else '本轮已修改代码'
    plan = [
        f'定位审查未通过的改动范围：{files}',
        f'修复代码审查失败项：{", ".join(failed) if failed else "review gates"}',
        '核对实现逻辑与原始任务目标一致，避免扩大改动范围',
    ]
    if side_effect_risk and side_effect_risk > 0:
        plan.append('降低潜在副作用风险，补充边界条件或回滚保护')
    for suggestion in suggestions[:3]:
        step = f'处理审查建议：{_shorten(suggestion, _INLINE_TEXT_LIMIT)}'
        if step not in plan:
            plan.append(step)
    plan.append('重新提交代码审查，要求 logic_correctness=true、consistency=true、side_effect_risk=0')

    return TaskPlan(
        task_id=task_id,
        report_id=report_id,
        module='code_review',
        change_type='fix',
        goal='修复代码审查反馈直到审查门禁通过',
        plan=plan[:_MAX_PLAN_STEPS],
        risk=3 if side_effect_risk and side_effect_risk > 1 else 2,
        priority=1,
        trigger_metric='code_review_gate',
        evidence=_dedupe_texts(evidence, limit=8),
        change_targets=_to_dict_list(report_context.get('change_targets')),
        report_context=report_context,
    )


def _build_validation_feedback_task(
    report: Mapping[str, Any],
    root: Path,
    validation_result: Mapping[str, Any],
    gate: Mapping[str, Any],
    target_files: Sequence[str],
    *,
    task_id: str,
    report_id: str,
) -> TaskPlan:
    failed = _to_str_list(gate.get('failed_gates'))
    failed_details = _failed_validation_details(validation_result)
    failed_cases = _failed_case_validations(validation_result)
    description = str(validation_result.get('description') or '').strip()
    hints = _to_str_list(validation_result.get('next_round_hints'))[:6]
    report_context = (
        _build_feedback_report_context(
            report, root, validation_result, feedback_kind='validation',
            case_ids=failed_cases,
        )
        if _validation_has_explicit_report_context(validation_result)
        else {}
    )
    effective_target_files = target_files if report_context else []
    files = '、'.join(effective_target_files[:4]) if effective_target_files else '本轮已修改代码'

    plan = [
        f'定位测试未通过的改动范围：{files}',
        f'优先复现失败门禁：{", ".join(failed) if failed else "validation gates"}',
    ]
    for detail in failed_details[:4]:
        command = str(detail.get('command') or detail.get('name') or '').strip()
        stderr = _shorten(str(detail.get('stderr') or ''), _INLINE_TEXT_LIMIT)
        if command and stderr:
            plan.append(f'修复失败用例 {detail.get("name")}: `{command}`，错误：{stderr}')
        elif command:
            plan.append(f'修复失败用例 {detail.get("name")}: `{command}`')
    if failed_cases:
        plan.append(f'修复 case 验证失败：{", ".join(failed_cases[:6])}')
    for hint in hints[:3]:
        plan.append(f'处理下一轮提示：{_shorten(hint, _INLINE_TEXT_LIMIT)}')
    plan.append('重新运行单元测试和 pipeline 测试，要求 unit_test=true、pipeline_test=true')

    evidence = [f'测试验证未通过：{", ".join(failed)}'] if failed else []
    if description:
        evidence.append(description)
    for detail in failed_details:
        evidence.append(_format_validation_detail(detail))
    for case_id in failed_cases:
        evidence.append(f'case_validation failed: {case_id}')
    evidence.extend(hints)
    evidence.extend(_to_str_list(report_context.get('evidence'))[:4])

    return TaskPlan(
        task_id=task_id,
        report_id=report_id,
        module='test_validation',
        change_type='fix',
        goal='修复测试验证反馈直到测试门禁通过',
        plan=_dedupe(plan)[:_MAX_PLAN_STEPS],
        risk=3 if any(str(d.get('type')) == 'pipeline' for d in failed_details) else 2,
        priority=2,
        trigger_metric='test_validation_gate',
        evidence=_dedupe_texts(evidence, limit=10),
        change_targets=_to_dict_list(report_context.get('change_targets')),
        report_context=report_context,
    )


def _build_feedback_report_context(
    report: Mapping[str, Any],
    root: Path,
    feedback: Mapping[str, Any],
    *,
    feedback_kind: str,
    case_ids: Sequence[str] = (),
) -> Dict[str, Any]:
    summary = report.get('summary') if isinstance(report.get('summary'), Mapping) else {}
    feedback_text = _feedback_text(feedback)
    target_modules = _feedback_related_modules(report, feedback_text, case_ids)
    actions = _related_report_actions(report, target_modules, feedback_text, case_ids)
    change_targets = _related_report_change_targets(report, root, target_modules, feedback_text)

    trigger_cases: List[str] = []
    validation_steps: List[str] = []
    for action in actions:
        trigger_cases.extend(_action_cases(action))
        if action.get('verification_metric'):
            validation_steps.append(f'验证 {action.get("verification_metric")} 指标改善')
        if action.get('rollback_metric'):
            validation_steps.append(f'确认 {action.get("rollback_metric")} 未退化，若退化则回滚')

    context: Dict[str, Any] = {
        'feedback_kind': feedback_kind,
        'top_issue': _shorten(str(summary.get('top_issue') or ''), 240),
        'related_modules': sorted(target_modules),
        'trigger_cases': _dedupe(trigger_cases)[:8],
        'evidence': _extract_evidence_from_actions(actions, limit=8),
        'change_targets': change_targets[:8],
        'validation_steps': _dedupe(validation_steps)[:8],
    }
    return {k: _json_safe(v) for k, v in context.items() if v not in (None, '', [], {})}


def _validation_has_explicit_report_context(validation_result: Mapping[str, Any]) -> bool:
    """Only enrich validation repair tasks when test output names concrete code context."""
    if _to_str_list(validation_result.get('next_round_hints')):
        return True
    for key in ('files', 'changed_files', 'related_files', 'modules', 'related_modules'):
        if _to_str_list(validation_result.get(key)):
            return True
    details = validation_result.get('details') or []
    if isinstance(details, list) and any(isinstance(detail, Mapping) for detail in details):
        return True
    return False


def _feedback_text(feedback: Mapping[str, Any]) -> str:
    parts: List[str] = []
    for key in ('description', 'summary', 'message', 'error'):
        if feedback.get(key):
            parts.append(str(feedback[key]))
    for key in ('suggestions', 'next_round_hints'):
        parts.extend(_to_str_list(feedback.get(key)))
    case_validation = feedback.get('case_validation')
    if isinstance(case_validation, Mapping):
        parts.extend(str(case_id) for case_id, ok in case_validation.items() if ok is not True)
    for detail in feedback.get('details') or []:
        if isinstance(detail, Mapping):
            parts.append(_format_validation_detail(detail))
    return '\n'.join(parts)


def _feedback_related_modules(
    report: Mapping[str, Any],
    feedback_text: str,
    case_ids: Sequence[str],
) -> set:
    modules = _modules_from_file_mentions(feedback_text)

    modification_plans = report.get('modification_plan') or []
    if isinstance(modification_plans, list):
        for mod_plan in modification_plans:
            if not isinstance(mod_plan, Mapping):
                continue
            stage = _canonical_module(str(mod_plan.get('stage') or ''))
            if stage != 'unknown' and _mapping_mentions_text(mod_plan, feedback_text):
                modules.add(stage)

    if not modules:
        modules.update(_modules_from_text_scores(feedback_text))

    if not modules:
        chain_map = dict(_iter_causal_chain_infos(report))
        for case_id in case_ids:
            chain_info = chain_map.get(str(case_id))
            if chain_info:
                module = _canonical_module(str(chain_info.get('bottleneck_stage') or ''))
                if module != 'unknown':
                    modules.add(module)

    action_list = report.get('action_list') or {}
    if not modules and isinstance(action_list, Mapping):
        for _, action in _sorted_actions(action_list):
            if not isinstance(action, Mapping):
                continue
            action_cases = set(_action_cases(action))
            if case_ids and action_cases.intersection(str(case_id) for case_id in case_ids):
                modules.add(_infer_module(action, {}, {}))

    if not modules:
        modules.update(_bottleneck_modules(report)[:1])
    return {module for module in modules if module and module != 'unknown'}


def _modules_from_file_mentions(text: str) -> set:
    lowered = text.lower()
    return {
        module
        for module, files in _PREFERRED_FILES.items()
        if any(Path(file_path).name.lower() in lowered or file_path.lower() in lowered for file_path in files)
    }


def _modules_from_text_scores(text: str) -> set:
    return {module for module, score in _module_text_scores(text).items() if score > 0}


def _related_report_actions(
    report: Mapping[str, Any],
    modules: set,
    feedback_text: str,
    case_ids: Sequence[str],
) -> List[Mapping[str, Any]]:
    action_list = report.get('action_list') or {}
    if not isinstance(action_list, Mapping):
        return []
    related: List[Mapping[str, Any]] = []
    case_set = {str(case_id) for case_id in case_ids}
    for _, action in _sorted_actions(action_list):
        if not isinstance(action, Mapping):
            continue
        module = _infer_module(action, {}, {})
        action_cases = set(_action_cases(action))
        if module in modules or (case_set and action_cases.intersection(case_set)) or _mapping_mentions_text(action, feedback_text):
            related.append(action)
        if len(related) >= 4:
            break
    return related


def _related_report_change_targets(
    report: Mapping[str, Any],
    root: Path,
    modules: set,
    feedback_text: str,
) -> List[Dict[str, Any]]:
    records: List[_Record] = []
    modification_plans = report.get('modification_plan') or []
    if isinstance(modification_plans, list):
        for index, mod_plan in enumerate(modification_plans):
            if not isinstance(mod_plan, Mapping):
                continue
            stage = _canonical_module(str(mod_plan.get('stage') or ''))
            if stage in modules or _mapping_mentions_text(mod_plan, feedback_text):
                records.append(_Record(f'feedback_modification_{index}', {}, {}, mod_plan))
    return _collect_change_targets(root, records) if records else []


def _mapping_mentions_text(value: Mapping[str, Any], feedback_text: str) -> bool:
    if not feedback_text:
        return False
    lowered = feedback_text.lower()
    return any(term.lower() in lowered for term in _mapping_search_terms(value) if term)


def _mapping_search_terms(value: Any) -> List[str]:
    raw_terms: List[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key) in {'file', 'param', 'current_raw', 'stage', 'module'} and item:
                raw_terms.append(Path(str(item)).name if str(key) == 'file' else str(item))
            raw_terms.extend(_mapping_search_terms(item))
    elif isinstance(value, list):
        for item in value:
            raw_terms.extend(_mapping_search_terms(item))
    elif isinstance(value, str):
        raw_terms.extend(Path(token).name if '/' in token else token
                         for token in re.findall(r'[A-Za-z_][A-Za-z0-9_./-]{2,}', value))
    return _dedupe(raw_terms)


def _build_module_task(
    report: Mapping[str, Any],
    root: Path,
    module: str,
    records: Sequence[_Record],
    *,
    task_id: str,
    priority: int,
    tid_map: Mapping[str, str],
) -> TaskPlan:
    rep_action = records[0].action
    rep_finding = records[0].finding
    rep_mod_plan = records[0].mod_plan

    evidence = _collect_evidence(report, module, records)
    change_targets = _collect_change_targets(root, records)
    target_files = _collect_target_files(root, module, records, change_targets)
    validation = _collect_validation(records)
    rollback = _collect_rollback(records)
    risk = max(_compute_risk(record.action, record.finding) for record in records)

    # --- Dynamic goal (not hardcoded) ---
    goal = _dynamic_goal(module, report, records)

    # --- Plan steps ---
    plan = _build_plan_steps(module, records, evidence, change_targets, target_files, validation, rollback)

    # --- New fields extracted from report ---
    trigger_cases = _collect_trigger_cases(records)
    trigger_metric = str(rep_action.get('trigger_metric') or '')
    confidence = _collect_confidence(records)
    cascade_type = _find_cascade_type(report, module)
    bottleneck_stage = _find_bottleneck_stage(report, module)

    return TaskPlan(
        task_id=task_id,
        report_id=_report_id(report),
        module=module,
        change_type=_change_type(rep_mod_plan or rep_action),
        goal=goal,
        plan=plan,
        risk=risk,
        priority=priority,
        trigger_cases=trigger_cases,
        trigger_metric=trigger_metric,
        confidence=confidence,
        cascade_type=cascade_type,
        bottleneck_stage=bottleneck_stage,
        evidence=evidence,
        change_targets=change_targets,
        depends_on=[tid_map[d] for d in _MODULE_DEPENDENCIES.get(module, []) if d in tid_map],
    )


# ---------------------------------------------------------------------------
# Dynamic goal (replaces hardcoded goals)
# ---------------------------------------------------------------------------

_FALLBACK_GOALS: Dict[str, str] = {
    'retriever': '提升检索召回率与相关文档命中率',
    'query_rewriter': '提升长查询和陈述式查询的意图聚焦能力',
    'chunker': '提升 chunk 语义完整性与覆盖率',
    'generator': '降低无相关上下文时的幻觉风险',
}


def _dynamic_goal(
    module: str,
    report: Mapping[str, Any],
    records: Sequence[_Record],
) -> str:
    # Priority 0: explicit action.changes[module].goal
    mod_plan_goals = [
        str(record.mod_plan.get('goal'))
        for record in records
        if isinstance(record.mod_plan, Mapping) and record.mod_plan.get('goal')
    ]
    combined = _combine_goal_texts(mod_plan_goals)
    if combined:
        return combined

    # Priority 1: action hypothesis (most specific)
    combined = _combine_goal_texts(str(record.action.get('hypothesis')) for record in records
                                   if record.action.get('hypothesis'))
    if combined:
        return combined

    # Priority 2: report summary top_issue
    summary = report.get('summary') if isinstance(report.get('summary'), Mapping) else {}
    top_issue = summary.get('top_issue')
    if top_issue:
        return _shorten(str(top_issue), _GOAL_TEXT_LIMIT)

    # Priority 3: finding behavior
    combined = _combine_goal_texts(str(record.finding.get('behavior')) for record in records
                                   if record.finding.get('behavior'))
    if combined:
        return combined

    # Fallback: template
    return _FALLBACK_GOALS.get(module, f'修复 {module} 阶段的核心指标退化')


def _combine_goal_texts(items: Iterable[str]) -> str:
    texts = _dedupe_texts(items, limit=4)
    if not texts:
        return ''
    if len(texts) == 1:
        return _shorten(texts[0], _GOAL_TEXT_LIMIT)

    separator = '；'
    for count in range(len(texts), 0, -1):
        per_item_limit = max(24, (_GOAL_TEXT_LIMIT - len(separator) * (count - 1)) // count)
        candidate = separator.join(_shorten(text, per_item_limit) for text in texts[:count])
        if len(candidate) <= _GOAL_TEXT_LIMIT:
            return candidate
    return _shorten(texts[0], _GOAL_TEXT_LIMIT)


# ---------------------------------------------------------------------------
# New field extractors
# ---------------------------------------------------------------------------

def _collect_trigger_cases(records: Sequence[_Record]) -> List[str]:
    cases: List[str] = []
    for record in records:
        for case in _action_cases(record.action):
            if str(case) not in cases:
                cases.append(str(case))
    return cases


def _action_cases(action: Mapping[str, Any]) -> List[str]:
    return _dedupe(_to_str_list(action.get('trigger_cases')) + _to_str_list(action.get('validation_cases')))


def _extract_evidence_from_actions(actions: Sequence[Mapping[str, Any]], *, limit: int = 12) -> List[str]:
    items: List[str] = []
    for action in actions:
        for key in ('symptoms', 'hypothesis', 'evidence_finding'):
            if action.get(key):
                items.append(str(action[key]))
    return _dedupe_texts(items, limit=limit)


def _collect_confidence(records: Sequence[_Record]) -> float:
    confidences = []
    for record in records:
        conf = record.action.get('evidence_confidence')
        if conf is not None:
            try:
                confidences.append(float(conf))
            except (TypeError, ValueError):
                pass
    return round(sum(confidences) / len(confidences), 2) if confidences else 0.0


def _collect_output_case_context(
    report: Mapping[str, Any],
    task_plans: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    trigger_cases_raw: List[str] = []
    for task in task_plans:
        if isinstance(task, Mapping):
            trigger_cases_raw.extend(_to_str_list(task.get('trigger_cases')))
    trigger_cases = _dedupe(trigger_cases_raw)

    chain_items = list(_iter_causal_chain_infos(report))
    chain_map = {case_id: info for case_id, info in chain_items}
    case_ids = trigger_cases or [case_id for case_id, _ in chain_items[:1]]
    for case_id in case_ids:
        chain_info = chain_map.get(str(case_id))
        if chain_info is None:
            continue
        module = _canonical_module(str(chain_info.get('bottleneck_stage') or 'unknown'))
        return _format_case_context(str(case_id), chain_info, module)
    return {}


def _iter_causal_chain_infos(report: Mapping[str, Any]) -> Iterable[Tuple[str, Mapping[str, Any]]]:
    chains = report.get('causal_chains') or {}
    if not isinstance(chains, Mapping):
        return
    for case_id, info in chains.items():
        if isinstance(info, Mapping):
            yield str(case_id), info


def _format_case_context(case_id: str, chain_info: Mapping[str, Any], module: str) -> Dict[str, Any]:
    chain = chain_info.get('chain') or []
    stage_trace: List[Dict[str, Any]] = []
    query = ''
    if isinstance(chain, list):
        for step in chain:
            if not isinstance(step, Mapping):
                continue
            stage = _canonical_module(str(step.get('stage') or ''))
            if not query:
                query = _extract_query_from_summary(str(step.get('input_summary') or ''))
            item: Dict[str, Any] = {
                'stage': str(step.get('stage') or stage),
                'relevant_to_task': stage == module or _canonical_module(str(chain_info.get('bottleneck_stage') or '')) == module,
                'input_summary': _shorten(str(step.get('input_summary') or ''), 220),
                'output_summary': _shorten(str(step.get('output_summary') or ''), 220),
                'information_lost': _shorten(str(step.get('information_lost') or ''), 320),
                'impact_score': step.get('impact_score'),
            }
            details = _case_step_details(step)
            if details:
                item['details'] = details
            survival = step.get('segment_survival')
            if isinstance(survival, Mapping):
                item['segment_survival'] = _compact_mapping(
                    survival,
                    ('recall', 'matched', 'partial', 'lost', 'total', 'precision'),
                )
            stage_trace.append({k: v for k, v in item.items() if v not in (None, '', {})})

    context: Dict[str, Any] = {
        'case_id': case_id,
        'dataset_id': chain_info.get('dataset_id') or case_id,
        'bottleneck_stage': chain_info.get('bottleneck_stage'),
        'bottleneck_impact': chain_info.get('bottleneck_impact'),
        'query': query,
        'stage_trace': stage_trace,
    }
    segment_summary = chain_info.get('segment_survival_summary')
    if isinstance(segment_summary, Mapping):
        context['segment_survival_summary'] = _compact_mapping(
            segment_summary,
            ('total_gt_segments', 'final_matched', 'final_partial', 'final_lost'),
        )
    segment_samples = _case_segment_samples(chain_info)
    if segment_samples:
        context['segment_samples'] = segment_samples
    return {k: _json_safe(v) for k, v in context.items() if v not in (None, '', [], {})}


def _extract_query_from_summary(summary: str) -> str:
    match = re.search(r'Query:\s*(.+)', summary)
    return _shorten(match.group(1).strip(), 320) if match else ''


def _case_step_details(step: Mapping[str, Any]) -> Dict[str, Any]:
    details = step.get('details')
    if not isinstance(details, Mapping):
        return {}
    return _compact_mapping(
        details,
        (
            'chunks_retrieved', 'gt_segments', 'recall_heuristic', 'matched', 'partial',
            'lost', 'key_hit_rate', 'faithfulness', 'missing_keys',
            'answer_semantic_similarity', 'semantic_impact', 'precision',
        ),
    )


def _case_segment_samples(chain_info: Mapping[str, Any]) -> List[Dict[str, Any]]:
    tracking = chain_info.get('segment_tracking') or []
    if not isinstance(tracking, list):
        return []
    samples: List[Dict[str, Any]] = []
    for item in tracking[:5]:
        if not isinstance(item, Mapping):
            continue
        sample: Dict[str, Any] = {
            'gt_index': item.get('gt_index'),
            'gt_preview': _shorten(str(item.get('gt_preview') or ''), 220),
        }
        stages = item.get('stages')
        if isinstance(stages, Mapping):
            stage_status: Dict[str, Any] = {}
            for stage_name, stage_info in stages.items():
                if isinstance(stage_info, Mapping):
                    stage_status[str(stage_name)] = _compact_mapping(stage_info, ('similarity', 'status'))
            if stage_status:
                sample['stages'] = stage_status
        samples.append({k: v for k, v in sample.items() if v not in (None, '', {})})
    return samples


def _compact_mapping(value: Mapping[str, Any], keys: Sequence[str]) -> Dict[str, Any]:
    return {key: _json_safe(value.get(key)) for key in keys if value.get(key) is not None}


def _find_cascade_type(report: Mapping[str, Any], module: str) -> str:
    effects = report.get('interaction_effects') or []
    if not isinstance(effects, list):
        return ''
    for effect in effects:
        if not isinstance(effect, Mapping):
            continue
        stages = effect.get('stages') or effect.get('path') or []
        modules = {_canonical_module(str(s)) for s in stages if s}
        if module in modules:
            ct = effect.get('cascade_type')
            if ct:
                return str(ct)
    return ''


def _find_bottleneck_stage(report: Mapping[str, Any], module: str) -> str:
    for _, chain_info in _iter_causal_chain_infos(report):
        bottleneck = _canonical_module(str(chain_info.get('bottleneck_stage') or ''))
        if bottleneck == module:
            return str(chain_info.get('bottleneck_stage') or '')
    return ''


# ---------------------------------------------------------------------------
# Evidence collection
# ---------------------------------------------------------------------------

def _collect_evidence(
    report: Mapping[str, Any], module: str, records: Sequence[_Record],
) -> List[str]:
    items: List[str] = _extract_evidence_from_actions([record.action for record in records], limit=24)
    for record in records:
        finding = record.finding
        mod_plan = record.mod_plan
        if finding.get('behavior'):
            items.append(str(finding['behavior']))
        if mod_plan.get('hypothesis'):
            items.append(str(mod_plan['hypothesis']))

    # interaction_effects evidence
    for effect in (report.get('interaction_effects') or []):
        if not isinstance(effect, Mapping):
            continue
        stages = {_canonical_module(str(s)) for s in (effect.get('stages') or effect.get('path') or []) if s}
        if module not in stages:
            continue
        if effect.get('description'):
            items.append(str(effect['description']))
        if effect.get('suggested_fix'):
            items.append(f'建议修复：{effect["suggested_fix"]}')
        ev = effect.get('evidence')
        if isinstance(ev, list):
            items.extend(str(e) for e in ev)
        elif ev:
            items.append(str(ev))

    # causal_chains evidence
    for case_id, chain_info in _iter_causal_chain_infos(report):
        if _canonical_module(str(chain_info.get('bottleneck_stage') or '')) == module:
            items.append(f'{case_id} bottleneck_stage={chain_info.get("bottleneck_stage")}, '
                         f'impact={chain_info.get("bottleneck_impact")}')
        for step in (chain_info.get('chain') or []):
            if not isinstance(step, Mapping):
                continue
            if _canonical_module(str(step.get('stage') or '')) != module:
                continue
            summary = step.get('information_lost') or step.get('output_summary')
            if summary:
                items.append(f'{case_id}: {summary}')
            details = step.get('details')
            if isinstance(details, Mapping):
                missing = details.get('missing_keys')
                if isinstance(missing, list) and missing:
                    items.append(f'{case_id} missing_keys={missing}')

    return _dedupe_texts(items, limit=12)


# ---------------------------------------------------------------------------
# Template plan step generation
# ---------------------------------------------------------------------------

def _build_plan_steps(
    module: str,
    records: Sequence[_Record],
    evidence: Sequence[str],
    change_targets: Sequence[Mapping[str, Any]],
    target_files: Sequence[str],
    validation: Sequence[str],
    rollback: Sequence[str],
) -> List[str]:
    """Build deterministic plan steps from _STEPS_TEMPLATE and _EVIDENCE_KEYWORDS."""
    explicit_steps: List[str] = []
    for record in records:
        mod_plan = record.mod_plan
        if isinstance(mod_plan, Mapping):
            explicit_steps.extend(_to_str_list(mod_plan.get('plan') or mod_plan.get('steps')))
    if explicit_steps:
        steps = _dedupe(explicit_steps)
    else:
        files = '、'.join(target_files[:4]) if target_files else '相关模块代码'
        params = '、'.join(str(t.get('param')) for t in change_targets if t.get('param'))
        key_ev = _select_key_evidence(module, evidence)

        template = _STEPS_TEMPLATE.get(module)
        if template:
            steps = [
                step_tmpl.format(
                    files=files,
                    evidence=key_ev or '触发案例指标退化',
                    params=params or '相关可调参数',
                )
                for step_tmpl in template
            ]
        else:
            rep_action = records[0].action
            steps = [
                f'定位 {module} 相关实现：{files}',
                '根据 report 假设复现触发案例并确认指标退化点',
                '实施最小可验证改动并记录回滚条件',
            ]
            symptoms = str(rep_action.get('symptoms') or '').strip()
            ev_text = str(rep_action.get('evidence_finding') or rep_action.get('hypothesis') or '').strip()
            if symptoms:
                steps.insert(1, f'核对症状：{_shorten(symptoms, _INLINE_TEXT_LIMIT)}')
            if ev_text:
                steps.insert(min(2, len(steps)), f'核对证据：{_shorten(ev_text, _INLINE_TEXT_LIMIT)}')

    for step in list(validation) + list(rollback):
        if step not in steps:
            steps.append(step)

    return steps[:_MAX_PLAN_STEPS]


def _select_key_evidence(module: str, evidence: Sequence[str]) -> str:
    if not evidence:
        return ''
    keywords = _EVIDENCE_KEYWORDS.get(module, ())
    if not keywords:
        return _shorten(str(evidence[0]), _KEY_EVIDENCE_LIMIT)

    scored: List[Tuple[int, int, str]] = []
    for i, item in enumerate(evidence):
        text = str(item)
        score = sum(_keyword_hits(text, kw) for kw in keywords)
        scored.append((score, -i, text))
    scored.sort(reverse=True)
    return _shorten(scored[0][2], _KEY_EVIDENCE_LIMIT)


def _keyword_hits(text: str, keyword: str) -> int:
    if not keyword:
        return 0
    flags = re.IGNORECASE if keyword.isascii() else 0
    if re.fullmatch(r'[A-Za-z0-9_]+', keyword):
        pattern = rf'(?<![A-Za-z0-9_]){re.escape(keyword)}(?![A-Za-z0-9_])'
        return len(re.findall(pattern, text, flags=flags))
    return text.lower().count(keyword.lower())


# ---------------------------------------------------------------------------
# Change targets, target files, validation, rollback
# ---------------------------------------------------------------------------

def _collect_change_targets(root: Path, records: Sequence[_Record]) -> List[Dict[str, Any]]:
    targets: List[Dict[str, Any]] = []
    for record in records:
        mod_plan = record.mod_plan
        for item in (mod_plan.get('suggested_changes') or []):
            if not isinstance(item, Mapping):
                continue
            file_path = str(item.get('file') or '')
            resolved = _resolve_file(root, file_path) if file_path else None
            target = {
                'file': _display_path(resolved, root) if resolved else file_path,
                'param': item.get('param'),
                'line': item.get('line'),
                'current_raw': item.get('current_raw'),
                'suggested_action': item.get('suggested_action'),
                'risk_level': item.get('risk_level'),
            }
            targets.append({k: v for k, v in target.items() if v not in (None, '')})
    return _dedupe_dicts(targets)


def _collect_target_files(
    root: Path,
    module: str,
    records: Sequence[_Record],
    change_targets: Sequence[Mapping[str, Any]],
) -> List[str]:
    preferred = _preferred_file_hints(root, module)
    if preferred:
        return preferred[:8]

    files: List[str] = []
    files.extend(str(target['file']) for target in change_targets if target.get('file'))
    for record in records:
        files.extend(_collect_code_hints(root, module, record.action, record.mod_plan))
    return _dedupe(files)[:8]


def _collect_validation(records: Sequence[_Record]) -> List[str]:
    steps: List[str] = []
    for record in records:
        action = record.action
        mod_plan = record.mod_plan
        validation = action.get('validation') or action.get('validation_cases') or []
        if isinstance(validation, str):
            validation = [validation]
        if validation:
            steps.append(f'使用触发案例复测：{", ".join(str(v) for v in validation)}')

        metric = action.get('verification_metric') or action.get('trigger_metric')
        rollback = action.get('rollback_metric')
        if metric:
            steps.append(f'验证 {metric} 指标改善')
        if rollback:
            steps.append(f'确认 {rollback} 未退化，若退化则回滚')

        mod_validation = mod_plan.get('verification_steps') if isinstance(mod_plan, Mapping) else None
        if isinstance(mod_validation, list):
            for item in mod_validation:
                text = _normalize_validation_step(str(item).strip())
                if text and text not in steps:
                    steps.append(text)
    return _dedupe(steps)


def _collect_rollback(records: Sequence[_Record]) -> List[str]:
    notes: List[str] = []
    for record in records:
        action = record.action
        mod_plan = record.mod_plan
        rm = action.get('rollback_metric')
        if rm:
            notes.append(f'若 {rm} 退化则回滚')
        rn = mod_plan.get('rollback_notes') if isinstance(mod_plan, Mapping) else None
        if rn:
            rn_str = str(rn)
            match = re.match(r'Revert changes if\s+(.+?)\s+drops', rn_str, flags=re.IGNORECASE)
            notes.append(f'若 {match.group(1)} 下降则回滚相关改动' if match else rn_str)
    return _dedupe(notes)


def _normalize_validation_step(step: str) -> str:
    m = re.match(r'\d+\.\s*Run evaluation on trigger cases:\s*(.+)', step, flags=re.IGNORECASE)
    if m:
        return f'使用触发案例复测：{m.group(1).strip().strip("[]").replace(chr(39), "").replace(chr(34), "")}'
    m = re.match(r'\d+\.\s*Monitor\s+(.+?)\s+for improvement', step, flags=re.IGNORECASE)
    if m:
        return f'验证 {m.group(1)} 指标改善'
    m = re.match(r'\d+\.\s*Check\s+(.+?)\s+has not degraded', step, flags=re.IGNORECASE)
    if m:
        return f'确认 {m.group(1)} 未退化，若退化则回滚'
    return step


# ---------------------------------------------------------------------------
# Downstream feedback gate handling
# ---------------------------------------------------------------------------

def _extract_feedback_mapping(
    *,
    explicit: Optional[Mapping[str, Any]],
    report: Mapping[str, Any],
    keys: Sequence[str],
) -> Mapping[str, Any]:
    if isinstance(explicit, Mapping):
        return _parse_feedback_mapping(explicit, keys)
    for source in (report, report.get('feedback'), report.get('downstream_results')):
        if not isinstance(source, Mapping):
            continue
        parsed = _parse_feedback_mapping(source, keys)
        if parsed:
            return parsed
    return {}


def _parse_feedback_mapping(value: Mapping[str, Any], keys: Sequence[str]) -> Mapping[str, Any]:
    wrapper_keys = list(keys)
    if any('review' in key.lower() for key in keys):
        wrapper_keys.extend(['ReviewResult', 'reviewResult'])
        direct_fields = {'logic_correctness', 'side_effect_risk', 'consistency', 'suggestions'}
    else:
        wrapper_keys.extend(['TestResult', 'testResult'])
        direct_fields = {'unit_test', 'pipeline_test', 'case_validation', 'details', 'next_round_hints'}

    for key in wrapper_keys:
        item = value.get(key)
        if isinstance(item, Mapping):
            return item

    lowered = {str(k).lower(): k for k in value}
    for key in wrapper_keys:
        original_key = lowered.get(str(key).lower())
        if original_key is not None and isinstance(value.get(original_key), Mapping):
            return value[original_key]

    return value if any(field in value for field in direct_fields) else {}


def _review_gate_status(review_result: Mapping[str, Any]) -> Dict[str, Any]:
    side_effect_risk = _parse_int(review_result.get('side_effect_risk'))
    checks = _true_field_checks(review_result, ('logic_correctness', 'consistency'))
    checks['side_effect_risk'] = side_effect_risk is not None and side_effect_risk <= 0
    return _gate_status(checks, side_effect_risk=side_effect_risk)


def _validation_gate_status(validation_result: Mapping[str, Any]) -> Dict[str, Any]:
    case_validation = validation_result.get('case_validation')
    checks = _true_field_checks(validation_result, ('unit_test', 'pipeline_test'))
    checks['case_validation'] = (
        all(value is True for value in case_validation.values())
        if isinstance(case_validation, Mapping)
        else True
    )
    return _gate_status(checks)


def _true_field_checks(result: Mapping[str, Any], fields: Sequence[str]) -> Dict[str, bool]:
    return {field: result.get(field) is True for field in fields}


def _gate_status(checks: Mapping[str, bool], **extra: Any) -> Dict[str, Any]:
    failed = [name for name, passed in checks.items() if not passed]
    status = {
        'passed': not failed,
        'failed_gates': failed,
    }
    status.update(extra)
    return status


def _failed_validation_details(validation_result: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    details = validation_result.get('details') or []
    if not isinstance(details, list):
        return []
    return [detail for detail in details if isinstance(detail, Mapping) and detail.get('passed') is not True]


def _failed_case_validations(validation_result: Mapping[str, Any]) -> List[str]:
    case_validation = validation_result.get('case_validation')
    if not isinstance(case_validation, Mapping):
        return []
    return [str(case_id) for case_id, passed in case_validation.items() if passed is not True]


def _format_validation_detail(detail: Mapping[str, Any]) -> str:
    parts = [
        f'type={detail.get("type")}',
        f'name={detail.get("name")}',
        f'command={detail.get("command")}',
        f'return_code={detail.get("return_code")}',
    ]
    stderr = str(detail.get('stderr') or '').strip()
    if stderr:
        parts.append(f'stderr={_shorten(stderr, _INLINE_TEXT_LIMIT)}')
    return ', '.join(part for part in parts if not part.endswith('=None'))


def _feedback_target_files(report: Mapping[str, Any], root: Path) -> List[str]:
    files: List[str] = []
    modification_plans = report.get('modification_plan') or []
    if isinstance(modification_plans, list):
        for item in modification_plans:
            if not isinstance(item, Mapping):
                continue
            files.extend(_collect_code_hints(root, _canonical_module(str(item.get('stage') or 'unknown')), {}, item))

    action_list = report.get('action_list') or {}
    if isinstance(action_list, Mapping):
        for _, raw_action in _sorted_actions(action_list):
            if not isinstance(raw_action, Mapping):
                continue
            module = _module_hint_from_action(raw_action)
            if module == 'unknown':
                module = _infer_module(raw_action, {}, {})
            files.extend(_collect_code_hints(root, module, raw_action, {}))
            if len(files) >= 8:
                break
    return _dedupe(files)[:8]


# ---------------------------------------------------------------------------
# Module inference and ranking
# ---------------------------------------------------------------------------

def _canonical_module(value: str) -> str:
    normalized = (value or '').strip().lower().replace(' ', '_')
    if normalized in _MODULE_ALIASES:
        return _MODULE_ALIASES[normalized]
    for key, mod in _MODULE_ALIASES.items():
        if key in normalized:
            return mod
    return normalized or 'unknown'


def _infer_module(
    action: Mapping[str, Any], finding: Mapping[str, Any], mod_plan: Optional[Mapping[str, Any]],
) -> str:
    # Try explicit fields first
    for candidate in [finding.get('field'), action.get('module'),
                      mod_plan.get('stage') if isinstance(mod_plan, Mapping) else None]:
        mod = _canonical_module(str(candidate or ''))
        if mod in _PREFERRED_FILES:
            return mod
    hint = _module_hint_from_action(action)
    if hint != 'unknown':
        return hint

    module, score = _best_scored_module(_action_text(action))
    return module if score > 0 else 'unknown'


def _best_scored_module(text: str) -> Tuple[str, int]:
    tie_break_order = {'generator': 3, 'query_rewriter': 2, 'chunker': 1, 'retriever': 0}
    return max(_module_text_scores(text).items(), key=lambda item: (item[1], tie_break_order[item[0]]))


def _module_text_scores(text: str) -> Dict[str, int]:
    lowered = text.lower()
    return {
        'retriever': sum(token in lowered for token in ('context_recall', 'doc_recall', 'retrieved', '检索', '召回')),
        'generator': sum(token in lowered for token in ('faithfulness', 'hallucination', '幻觉', '生成')),
        'query_rewriter': sum(token in lowered for token in ('rewrite', 'rewriter', 'compression', '改写', '查询')),
        'chunker': sum(token in lowered for token in ('chunk', '切块', '切分', '文本段', 'overlap')),
    }


def _action_text(action: Mapping[str, Any]) -> str:
    return ' '.join(str(action.get(k) or '') for k in
                    ('trigger_metric', 'owner_team_suggestion', 'symptoms', 'hypothesis', 'evidence_finding'))


def _module_hint_from_action(action: Mapping[str, Any]) -> str:
    owner = str(action.get('owner_team_suggestion') or '').lower()
    metric = str(action.get('trigger_metric') or '').lower()
    if 'retrieval' in owner or metric in {'context_recall', 'doc_recall'}:
        return 'retriever'
    if 'generation' in owner or 'llm' in owner or metric == 'faithfulness':
        return 'generator'
    if 'rewrite' in owner:
        return 'query_rewriter'
    return 'unknown'


def _rank_modules(
    report: Mapping[str, Any],
    grouped: Mapping[str, Sequence[_Record]],
) -> List[str]:
    bottlenecks = _bottleneck_modules(report)
    stage_scores = _chain_stage_scores(report)

    def sort_key(module: str) -> Tuple[int, int, int, float, str]:
        records = grouped[module]
        min_prio = min((_parse_int(record.action.get('priority')) or 9999) for record in records)
        bn_rank = bottlenecks.index(module) if module in bottlenecks else 999
        return bn_rank, min_prio, _DEFAULT_ORDER.get(module, 8), -stage_scores.get(module, 0), module

    return sorted(grouped, key=sort_key)


def _bottleneck_modules(report: Mapping[str, Any]) -> List[str]:
    modules: List[str] = []
    for _, info in _iter_causal_chain_infos(report):
        mod = _canonical_module(str(info.get('bottleneck_stage') or ''))
        if mod != 'unknown' and mod not in modules:
            modules.append(mod)
    return modules


def _chain_stage_scores(report: Mapping[str, Any]) -> Dict[str, float]:
    scores: Dict[str, float] = {}
    for _, info in _iter_causal_chain_infos(report):
        for step in (info.get('chain') or []):
            if not isinstance(step, Mapping):
                continue
            stage = _canonical_module(str(step.get('stage') or ''))
            if stage == 'unknown':
                continue
            try:
                impact = float(step.get('impact_score') or 0)
            except (TypeError, ValueError):
                impact = 0
            scores[stage] = scores.get(stage, 0) + impact
    return scores


# ---------------------------------------------------------------------------
# Finding and modification plan matching
# ---------------------------------------------------------------------------

def _matching_finding(report: Mapping[str, Any], action_key: str, action: Mapping[str, Any]) -> Mapping[str, Any]:
    """Match a finding to an action by inferred module, with index fallback."""
    findings = report.get('key_findings') or {}
    if not isinstance(findings, Mapping):
        return {}

    action_scores = _module_text_scores(_action_text(action))
    hinted_module = _module_hint_from_action(action)
    key_index = _index_from_key(action_key)
    best: Optional[Tuple[int, str, Mapping[str, Any]]] = None

    for finding_key, finding in findings.items():
        if not isinstance(finding, Mapping):
            continue
        field = _canonical_module(str(finding.get('field') or ''))
        score = action_scores.get(field, 0)
        if hinted_module != 'unknown' and field == hinted_module:
            score += 3
        if key_index is not None and _index_from_key(str(finding_key)) == key_index:
            score += 3
        if score <= 0:
            continue
        candidate = (score, str(finding_key), finding)
        if best is None or candidate[0] > best[0]:
            best = candidate
    if best is not None:
        return best[2]

    # Fallback: index-based
    if key_index is not None:
        for candidate_key in [f'finding_{key_index}']:
            f = findings.get(candidate_key)
            if isinstance(f, Mapping):
                return f
    return {}


def _matching_modification_plan(
    action: Mapping[str, Any], finding: Mapping[str, Any], modification_plans: Sequence[Any],
) -> Mapping[str, Any]:
    if not modification_plans:
        return {}
    valid_plans = [item for item in modification_plans if isinstance(item, Mapping)]
    if not valid_plans:
        return {}
    module = _infer_module(action, finding, None)
    for item in valid_plans:
        stage = _canonical_module(str(item.get('stage') or ''))
        if stage != 'unknown' and stage == module:
            return item
    if len(valid_plans) == 1 and valid_plans[0].get('suggested_changes'):
        raw_stage = str(valid_plans[0].get('stage') or '').strip()
        stage = _canonical_module(raw_stage)
        if not raw_stage or stage in ('unknown', module):
            return valid_plans[0]
    return {}


# ---------------------------------------------------------------------------
# Sorted actions
# ---------------------------------------------------------------------------

def _sorted_actions(action_list: Mapping[str, Any]) -> List[Tuple[str, Any]]:
    def sort_key(item: Tuple[str, Any]) -> Tuple[int, str]:
        key, action = item
        priority = action.get('priority') if isinstance(action, Mapping) else None
        try:
            return int(priority), key
        except (TypeError, ValueError):
            idx = _index_from_key(key)
            return (idx if idx is not None else 9999), key
    return sorted(action_list.items(), key=sort_key)


def _index_from_key(key: str) -> Optional[int]:
    match = re.search(r'(\d+)$', str(key))
    return int(match.group(1)) if match else None


# ---------------------------------------------------------------------------
# Code file hints and path resolution (simplified)
# ---------------------------------------------------------------------------

def _collect_code_hints(root: Path, module: str, action: Mapping[str, Any], mod_plan: Mapping[str, Any]) -> List[str]:
    hints: List[str] = _preferred_file_hints(root, module)
    # From report-referenced files
    for source in (action, mod_plan):
        for f in (source.get('files') or []) if isinstance(source, Mapping) else []:
            resolved = _resolve_file(root, str(f))
            if resolved:
                hints.append(_display_path(resolved, root))
        for item in (source.get('suggested_changes') or []) if isinstance(source, Mapping) else []:
            if isinstance(item, Mapping) and item.get('file'):
                resolved = _resolve_file(root, str(item['file']))
                if resolved:
                    hints.append(_display_path(resolved, root))
    # Keyword scan fallback
    if len(set(hints)) < 2:
        hints.extend(_keyword_scan(root, module, max_files=4))
    return _dedupe(hints)[:6]


def _preferred_file_hints(root: Path, module: str) -> List[str]:
    hints: List[str] = []
    for pref in _PREFERRED_FILES.get(module, []):
        for candidate in [root / pref, root / 'algorithm' / pref if not pref.startswith('algorithm/') else None,
                          root / pref.removeprefix('algorithm/') if pref.startswith('algorithm/') else None]:
            if candidate and candidate.exists():
                hints.append(_display_path(candidate.resolve(), root))
                break
    return _dedupe(hints)


def _resolve_file(root: Path, report_path: str) -> Optional[Path]:
    """Resolve a file path from the report against the code root."""
    raw = Path(report_path)
    if raw.exists():
        return raw.resolve()

    # Try various suffixes
    path_text = report_path.replace('\\', '/').lstrip('/')
    suffixes = [path_text]
    for marker in ('LazyRAG/', 'algorithm/', 'chat/', 'parsing/', 'evo/'):
        if marker in path_text:
            suffix = path_text.split(marker, 1)[1]
            suffixes.append(f'{marker}{suffix}' if marker != 'LazyRAG/' else suffix)

    for suffix in _dedupe(s.lstrip('/') for s in suffixes if s):
        for candidate in [root / suffix,
                          root / suffix.removeprefix('algorithm/') if suffix.startswith('algorithm/') else None,
                          root / 'algorithm' / suffix if not suffix.startswith('algorithm/') else None]:
            if candidate and candidate.exists():
                return candidate.resolve()

    # Basename fallback
    basename = raw.name
    if basename:
        scan_root = root / 'algorithm' if (root / 'algorithm').exists() else root
        for path in _iter_code_files(scan_root, basename=basename):
            if path.is_file():
                return path.resolve()
    return None


def _keyword_scan(root: Path, module: str, max_files: int) -> List[str]:
    keywords = _MODULE_KEYWORDS.get(module, ())
    if not keywords:
        return []
    scored: List[Tuple[int, Path]] = []
    scan_root = root / 'algorithm' if (root / 'algorithm').exists() else root
    for path in _iter_code_files(scan_root):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding='utf-8', errors='ignore')[:20000]
        except OSError:
            continue
        score = sum(text.count(kw) for kw in keywords)
        if score > 0:
            scored.append((score, path))
    scored.sort(key=lambda x: (-x[0], str(x[1])))
    return [_display_path(p, root) for _, p in scored[:max_files]]


def _iter_code_files(scan_root: Path, *, basename: Optional[str] = None) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(scan_root):
        dirnames[:] = [dirname for dirname in dirnames if dirname not in _IGNORED_DIRS]
        for filename in filenames:
            if basename is not None and filename != basename:
                continue
            path = Path(dirpath) / filename
            if path.suffix in _CODE_EXTENSIONS:
                yield path


def _display_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


# ---------------------------------------------------------------------------
# Risk computation
# ---------------------------------------------------------------------------

def _compute_risk(action: Mapping[str, Any], finding: Mapping[str, Any]) -> int:
    for value in (finding.get('severity'), finding.get('risk_level')):
        risk = _parse_risk(value)
        if risk is not None:
            return risk
    priority = _parse_int(action.get('priority'))
    if priority is None:
        return 2
    return 3 if priority <= 2 else (2 if priority <= 4 else 1)


def _parse_risk(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, str):
        lowered = value.lower().strip()
        mapping = {'critical': 3, 'high': 3, 'medium': 2, 'mid': 2, 'low': 1, 'none': 0, 'safe': 0}
        if lowered in mapping:
            return mapping[lowered]
    parsed = _parse_int(value)
    return max(0, min(3, parsed)) if parsed is not None else None


def _parse_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _change_type(change: Mapping[str, Any]) -> str:
    return str(change.get('type') or change.get('change_type') or 'modify')


# ---------------------------------------------------------------------------
# LLM-based plan generation (optional)
# ---------------------------------------------------------------------------

def _resolve_plan_model(plan_model_role: str) -> Any:
    try:
        try:
            from chat.pipelines.builders.get_models import get_automodel
        except ModuleNotFoundError:
            from algorithm.chat.pipelines.builders.get_models import get_automodel
        return get_automodel(plan_model_role)
    except Exception as exc:
        _trace_model_plan(f'failed to resolve model `{plan_model_role}`: {type(exc).__name__}: {exc}')
        return None


def _trace_model_plan(message: str) -> None:
    print(f'[task_planner:model] {message}')


def _model_plan_steps_for_tasks(plan_model: Any, tasks: Sequence[TaskPlan]) -> List[TaskPlan]:
    if not tasks:
        return []

    payload = [
        {
            'task_id': task.task_id,
            'module': task.module,
            'goal': task.goal,
            'risk': task.risk,
            'trigger_cases': task.trigger_cases,
            'trigger_metric': task.trigger_metric,
            'evidence': task.evidence,
            'change_targets': task.change_targets,
            'report_context': task.report_context,
            'depends_on': task.depends_on,
        }
        for task in tasks
    ]
    prompt = (
        '你是 LazyRAG 的任务规划器。请根据下面所有任务信息，一次性生成每个 TaskPlan.plan。\n'
        '要求：只输出 JSON 对象；key 是 task_id；value 是中文步骤字符串数组；每个数组长度 3-6；'
        '步骤要覆盖定位、改动、验证，避免泛泛而谈；不要复用固定模板句式，不要输出 Markdown。\n\n'
        f'{json.dumps(payload, ensure_ascii=False, indent=2)}'
    )
    _trace_model_plan(f'preparing one request for {len(tasks)} task(s); prompt chars={len(prompt)}')
    try:
        if JsonFormatter is not None and hasattr(plan_model, 'formatter'):
            plan_model = plan_model.formatter(JsonFormatter())
            _trace_model_plan('formatter attached for batch request')
        else:
            _trace_model_plan('formatter unavailable for batch request; using raw model response')
    except Exception as exc:
        _trace_model_plan(
            f'failed to attach formatter for batch request: {type(exc).__name__}: {exc}; '
            'using deterministic fallback steps'
        )
        return list(tasks)

    try:
        try:
            _trace_model_plan('calling model once with stream_output=False')
            response = plan_model(prompt, stream_output=False)
        except TypeError as exc:
            _trace_model_plan(
                f'model rejected stream_output: {type(exc).__name__}: {exc}; retrying without stream_output'
            )
            response = plan_model(prompt)
        _trace_model_plan(f'model returned; response type={type(response).__name__}')
    except Exception as exc:
        _trace_model_plan(
            f'model call failed: {type(exc).__name__}: {exc}; using deterministic fallback steps'
        )
        return list(tasks)

    plan_map = _parse_model_plan_map(response, tasks)
    if not plan_map:
        _trace_model_plan('could not parse model response; using deterministic fallback steps')
        return list(tasks)

    updated: List[TaskPlan] = []
    for task in tasks:
        steps = plan_map.get(task.task_id)
        if steps:
            _trace_model_plan(f'parsed {len(steps)} model step(s) for task `{task.task_id}` module `{task.module}`')
            updated.append(replace(task, plan=steps))
        else:
            _trace_model_plan(f'no model steps for task `{task.task_id}` module `{task.module}`; using fallback steps')
            updated.append(task)
    return updated


def _parse_model_plan_map(response: Any, tasks: Sequence[TaskPlan]) -> Dict[str, List[str]]:
    parsed = _coerce_model_response(response)
    if isinstance(parsed, str):
        parsed = _parse_jsonish_text(parsed)
    if isinstance(parsed, Mapping):
        result: Dict[str, List[str]] = {}
        module_to_task_ids: Dict[str, List[str]] = {}
        for task in tasks:
            module_to_task_ids.setdefault(task.module, []).append(task.task_id)
        for key, value in parsed.items():
            steps = _normalize_step_list(value)
            task_id = str(key)
            if not steps and isinstance(value, Mapping):
                steps = _normalize_step_list(value.get('plan') or value.get('steps'))
                task_id = str(value.get('task_id') or task_id)
            if not steps:
                continue
            task_ids = module_to_task_ids.get(task_id, [task_id])
            for resolved_task_id in task_ids:
                result[resolved_task_id] = steps
        return result
    if isinstance(parsed, list):
        result: Dict[str, List[str]] = {}
        for item in parsed:
            if not isinstance(item, Mapping):
                continue
            task_id = str(item.get('task_id') or item.get('id') or '')
            steps = _normalize_step_list(item.get('plan') or item.get('steps'))
            if task_id and steps:
                result[task_id] = steps
        if not result and len(tasks) == 1:
            steps = _normalize_step_list(parsed)
            if steps:
                result[tasks[0].task_id] = steps
        return result
    return {}


def _parse_jsonish_text(text: str) -> Any:
    text = text.strip()
    for candidate in _json_candidates(text):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return text


def _json_candidates(text: str) -> List[str]:
    candidates = [text]
    match = re.search(r'```(?:json)?\s*(.*?)```', text, flags=re.DOTALL | re.IGNORECASE)
    if match:
        candidates.append(match.group(1).strip())
    for opener, closer in (('{', '}'), ('[', ']')):
        start = text.find(opener)
        end = text.rfind(closer)
        if 0 <= start < end:
            candidates.append(text[start:end + 1])
    return _dedupe(candidates)


def _coerce_model_response(response: Any) -> Any:
    if isinstance(response, Mapping):
        for key in ('content', 'text', 'response', 'answer', 'output'):
            value = response.get(key)
            if isinstance(value, str):
                parsed = _parse_jsonish_text(value)
                if not isinstance(parsed, str):
                    return parsed
        return response
    if isinstance(response, list):
        return response
    text = _response_to_text(response)
    return text or None


def _normalize_step_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _response_to_text(response: Any) -> str:
    if response is None:
        return ''
    if isinstance(response, str):
        return response.strip()
    if isinstance(response, Mapping):
        for key in ('content', 'text', 'response', 'answer', 'output'):
            val = response.get(key)
            if isinstance(val, str):
                return val.strip()
        return json.dumps(response, ensure_ascii=False)
    if not isinstance(response, (bytes, bytearray)):
        try:
            return ''.join(str(item) for item in response).strip()
        except TypeError:
            pass
    return str(response).strip()


# ---------------------------------------------------------------------------
# Input normalization and output formatting
# ---------------------------------------------------------------------------

def _normalize_agent_input(
    *, report: Any, code_root: str | Path, output_format: str, kwargs: Mapping[str, Any],
) -> Tuple[Mapping[str, Any], Path, str, Mapping[str, Any], Mapping[str, Any]]:
    payload: Dict[str, Any] = {}
    if isinstance(report, Mapping) and _is_agent_payload(report):
        payload.update(report)
    elif report is not None:
        payload['report'] = report
    payload.update(kwargs)

    raw_report = payload.get('report') or payload.get('report_path')
    if raw_report is None:
        raise ValueError('TaskPlannerAgent requires `report` or `report_path` input.')

    resolved = load_report(raw_report) if isinstance(raw_report, (str, Path)) else raw_report
    if not isinstance(resolved, Mapping):
        raise ValueError('TaskPlannerAgent `report` input must be a mapping or a report JSON path.')

    review_result = _parse_feedback_mapping(
        payload,
        ('review_result', 'code_review_result', 'code_review', 'review', 'ReviewResult'),
    )
    validation_result = _parse_feedback_mapping(
        payload,
        ('validation_result', 'test_validation_result', 'test_result', 'test_validation', 'TestResult'),
    )
    resolved_root = Path(payload.get('code_root') or code_root)
    resolved_format = str(payload.get('format') or payload.get('output_format') or output_format)
    return resolved, resolved_root, resolved_format, review_result, validation_result


def _is_agent_payload(value: Mapping[str, Any]) -> bool:
    return any(k in value for k in (
        'report', 'report_path', 'code_root', 'format', 'output_format',
        'review_result', 'code_review_result', 'code_review', 'review', 'ReviewResult',
        'validation_result', 'test_validation_result', 'test_result', 'test_validation', 'TestResult',
    ))


def _report_id(report: Mapping[str, Any]) -> str:
    metadata = report.get('metadata') if isinstance(report.get('metadata'), Mapping) else {}
    return str(report.get('report_id') or metadata.get('report_id') or 'unknown_report')


def _format_task_output(
    tasks: Sequence[Mapping[str, Any]],
    report: Mapping[str, Any],
    fmt: str,
    *,
    schema: str = 'full',
) -> Any:
    """Single output path: always produce a JSON-safe task planning dict."""
    report_id = _report_id(report)
    summary = report.get('summary') if isinstance(report.get('summary'), Mapping) else {}
    top_issue = str(summary.get('top_issue') or '')

    task_plans = _normalize_tasks(tasks, report, schema=schema)
    status = _output_status(task_plans)
    has_feedback = status == 'repair_planned'
    case_context = {} if has_feedback else _collect_output_case_context(report, task_plans)

    output: Dict[str, Any] = {
        'report_id': report_id,
        'status': status,
        'top_issue': top_issue,
        'instruction': '你是代码执行 agent。请按下面的 task_plans 列表逐项处理，每个任务都要求最小可验证改动。',
        'constraints': list(_OPENCODE_CONSTRAINTS),
        'task_plans': task_plans,
    }
    if case_context:
        output['case'] = case_context

    if fmt in ('task_plans', 'list', 'raw'):
        return output
    return _dump_json(output)


def _normalize_tasks(
    tasks: Sequence[Mapping[str, Any]], report: Mapping[str, Any], *, schema: str = 'full',
) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for i, task in enumerate(tasks, start=1):
        if not isinstance(task, Mapping):
            task = {}
        risk = _parse_risk(task.get('risk'))
        priority = _parse_int(task.get('priority'))
        item: Dict[str, Any] = {
            'task_id': str(task.get('task_id') or f'T{i:03d}'),
            'report_id': str(task.get('report_id') or _report_id(report)),
            'module': str(task.get('module') or 'unknown'),
            'change_type': str(task.get('change_type') or 'modify'),
            'goal': str(task.get('goal') or ''),
            'plan': _to_str_list(task.get('plan')),
            'risk': risk if risk is not None else 2,
        }
        if priority is not None:
            item['priority'] = priority
        if schema != 'simple':
            for key, value in {
                'trigger_cases': _to_str_list(task.get('trigger_cases')),
                'trigger_metric': task.get('trigger_metric') or '',
                'confidence': task.get('confidence') or 0.0,
                'cascade_type': task.get('cascade_type') or '',
                'bottleneck_stage': task.get('bottleneck_stage') or '',
                'evidence': _to_str_list(task.get('evidence')),
                'change_targets': _to_dict_list(task.get('change_targets')),
                'report_context': _json_safe(task.get('report_context') or {}),
                'depends_on': _to_str_list(task.get('depends_on')),
            }.items():
                if value:
                    item[key] = value
        result.append(_json_safe(item))
    return result


def _output_status(task_plans: Sequence[Mapping[str, Any]]) -> str:
    if not task_plans:
        return 'no_repair_task'
    modules = {str(task.get('module') or '') for task in task_plans if isinstance(task, Mapping)}
    if modules & {'code_review', 'test_validation'}:
        return 'repair_planned'
    return 'planned'


# ---------------------------------------------------------------------------
# Utility functions (consolidated)
# ---------------------------------------------------------------------------

def _to_str_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, Mapping):
        return [json.dumps(_json_safe(value), ensure_ascii=False, sort_keys=True)]
    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _to_dict_list(value: Any) -> List[Dict[str, Any]]:
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    result: List[Dict[str, Any]] = []
    for item in items:
        if isinstance(item, Mapping):
            result.append({str(k): _json_safe(v) for k, v in item.items() if v not in (None, '')})
        else:
            text = str(item).strip()
            if text:
                result.append({'value': text})
    return _dedupe_dicts(result)


def _dedupe(items: Iterable[str]) -> List[str]:
    seen: set = set()
    result: List[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _dedupe_texts(items: Iterable[str], *, limit: int = 18) -> List[str]:
    """Dedupe text items by normalized prefix."""
    seen: set = set()
    result: List[str] = []
    for item in items:
        text = ' '.join(str(item).split())
        if not text:
            continue
        key = re.sub(r'\W+', '', text.lower())[:180]
        if key in seen:
            continue
        seen.add(key)
        result.append(_shorten(text, _EVIDENCE_TEXT_LIMIT))
        if len(result) >= limit:
            break
    return result


def _dedupe_dicts(items: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    seen: set = set()
    result: List[Dict[str, Any]] = []
    for item in items:
        normalized = _json_safe(item)
        key = _freeze_for_dedupe(normalized)
        if key in seen:
            continue
        seen.add(key)
        result.append(dict(normalized) if isinstance(normalized, Mapping) else dict(item))
    return result


def _freeze_for_dedupe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return tuple(sorted((str(k), _freeze_for_dedupe(v)) for k, v in value.items()))
    if isinstance(value, list):
        return tuple(_freeze_for_dedupe(item) for item in value)
    return value


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray, str)):
        return [_json_safe(item) for item in value]
    return str(value)


def _dump_json(value: Any, *, indent: Optional[int] = 2) -> str:
    return json.dumps(_json_safe(value), ensure_ascii=False, indent=indent, allow_nan=False)


def _shorten(text: str, limit: int) -> str:
    text = ' '.join(text.split())
    return text if len(text) <= limit else text[:limit - 3] + '...'


# ---------------------------------------------------------------------------
# Module API and lightweight test entrypoint
# ---------------------------------------------------------------------------

def generate_task_plan_output(
    report_path: str | Path,
    *,
    code_root: str | Path = _DEFAULT_CODE_ROOT,
    output: str | Path | None = None,
    output_format: str = 'json',
    schema: str = 'full',
    plan_model_role: str = 'llm_instruct',
    plan_mode: str = 'template',
    use_model_plan: bool = False,
    review_result: Optional[Mapping[str, Any]] = None,
    validation_result: Optional[Mapping[str, Any]] = None,
) -> Any:
    """Generate TaskPlan output from a report path.

    This is the module-level API. ``main`` below is intentionally only a thin
    smoke-test wrapper around this function.
    """
    resolved_plan_mode = _resolve_plan_mode(plan_mode, use_model_plan)
    print(f'[task_planner] plan_mode={resolved_plan_mode}')
    agent = TaskPlannerAgent(
        code_root=code_root,
        output_format=output_format,
        use_model_plan=(resolved_plan_mode == 'llm'),
    )
    return agent.forward(
        report_path=report_path,
        output_path=output or _default_plan_output_path(report_path),
        schema=schema,
        plan_model_role=plan_model_role,
        review_result=review_result,
        validation_result=validation_result,
    )


def _resolve_plan_mode(plan_mode: str, use_model_plan: bool) -> str:
    if use_model_plan:
        return 'llm'
    normalized = str(plan_mode or 'template').strip().lower()
    if normalized not in ('template', 'llm'):
        raise ValueError('plan_mode must be `template` or `llm`.')
    return normalized


def _write_output(value: Any, output: str | Path | None) -> None:
    text = value if isinstance(value, str) else _dump_json(value)
    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(text, encoding='utf-8')
    else:
        print(text)


def _default_plan_output_path(report_path: str | Path) -> Path:
    path = Path(report_path)
    return _PLAN_OUTPUT_DIR / f'{path.stem}_plan.json'


def _default_plan_output_path_for_report(report: Mapping[str, Any]) -> Path:
    return _PLAN_OUTPUT_DIR / f'{_report_id(report)}_plan.json'


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Manual smoke-test entrypoint; import this module for production use."""
    parser = argparse.ArgumentParser(
        description='Smoke-test TaskPlan generation from a badcase report JSON.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument('--report', required=True, help='Path to report JSON.')
    parser.add_argument('--format', choices=('json', 'raw'), default='json')
    parser.add_argument('--schema', choices=('full', 'simple'), default='full')
    parser.add_argument('--plan-model-role', default='llm_instruct')
    parser.add_argument('--plan-mode', choices=('template', 'llm'), default='template',
                        help='Use template steps or LLM-assisted plan generation.')
    parser.add_argument('--use-model-plan', action='store_true',
                        help='Backward-compatible alias for --plan-mode llm.')
    parser.add_argument('--review', help='Optional code review result JSON path.')
    parser.add_argument('--val', help='Optional test validation result JSON path.')
    args = parser.parse_args(argv)

    generate_task_plan_output(
        args.report,
        code_root=_DEFAULT_CODE_ROOT,
        output=None,
        output_format=args.format,
        schema=args.schema,
        plan_model_role=args.plan_model_role,
        plan_mode=args.plan_mode,
        use_model_plan=args.use_model_plan,
        review_result=load_report(args.review) if args.review else None,
        validation_result=load_report(args.val) if args.val else None,
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
