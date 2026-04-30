from __future__ import annotations
from typing import Any
from evo.conductor.synthesis import PRIORITY_ORDER
from evo.utils import coerce_confidence
_PRIORITY_MAP = {'P0': '🔴 P0', 'P1': '🟡 P1', 'P2': '🔵 P2'}
def _priority_rank(value: Any) -> int:
    try:
        return PRIORITY_ORDER.index(value)
    except ValueError:
        return len(PRIORITY_ORDER)
def _validity_badge(score: float) -> str:
    if score >= 0.7:
        return f'✓ {score:.2f}'
    if score >= 0.4:
        return f'⚠ {score:.2f}'
    return f'✗ {score:.2f}'
def _esc(text: Any) -> str:
    return str(text or '').replace('|', '\\|').replace('\n', ' ')
def _action_title(a: dict[str, Any]) -> str:
    title = str(a.get('title') or '').strip()
    if title:
        return title
    rationale = str(a.get('rationale') or a.get('suggested_changes') or '').strip()
    if rationale:
        return rationale[:80] + ('…' if len(rationale) > 80 else '')
    return f"[{a.get('id', '?')}]"
def _action_change(a: dict[str, Any]) -> str:
    text = str(a.get('suggested_changes') or '').strip()
    if text:
        return text
    rationale = str(a.get('rationale') or '').strip()
    return rationale or '—'
def json_to_markdown(data: dict[str, Any]) -> str:
    meta = data.get('metadata', {})
    report_id = data.get('report_id', 'N/A')
    created_at = meta.get('created_at', 'N/A')
    pipeline = ', '.join((f'`{s}`' for s in meta.get('pipeline', [])))
    total = meta.get('total_cases', 0)
    summary = data.get('summary', '')
    guidance = data.get('guidance', '')
    iterations = data.get('synthesizer_iterations', 0)
    md: list[str] = ['# RAG 诊断报告', f'**报告**：`{report_id}` | **时间**：{created_at} | **case 数**：{total} | **Synthesizer 轮次**：{iterations}', f'**Pipeline**：{pipeline}', '', '## 核心结论', summary or '_（无）_']
    actions = data.get('actions', []) or []
    in_scope = [a for a in actions if a.get('code_map_in_scope')]
    out_scope = [a for a in actions if not a.get('code_map_in_scope')]
    md.append('\n## 改进建议')
    if not in_scope:
        md.append('_无落入 code_map 的可执行 action。_')
    else:
        sorted_in = sorted(in_scope, key=lambda a: (_priority_rank(a.get('priority')), -float(a.get('validity_score', 0) or 0)))
        md.append('| 优先级 | 标题 | 修改方向 | 落点 | 影响指标 | 置信度 | 验证度 |')
        md.append('| :--- | :--- | :--- | :--- | :--- | :--- | :--- |')
        for a in sorted_in:
            prio = _PRIORITY_MAP.get(a.get('priority'), a.get('priority', 'P?'))
            metric = a.get('expected_impact_metric', '')
            direction = a.get('expected_direction', '')
            impact = f'`{metric}` {direction}' if metric else '—'
            target = a.get('code_map_target') or '—'
            line = a.get('target_line') or 0
            scope_cell = f'`{target}`' + (f':{line}' if line else '')
            md.append(f"| {prio} | **{_esc(_action_title(a))}** | {_esc(_action_change(a))} | {scope_cell} | {impact} | {int(coerce_confidence(a.get('confidence'), 0.0) * 100)}% | {_validity_badge(float(a.get('validity_score', 0) or 0))} |")
        md.append('\n### 行动详情')
        for a in sorted_in:
            md.append(f"\n#### [{a.get('id')}] {_action_title(a)}  ({a.get('priority')})")
            md.append(f'- **修改方向**: {_action_change(a)}')
            target = a.get('code_map_target') or '—'
            line = a.get('target_line') or 0
            step = a.get('target_step') or ''
            loc = f'`{target}`' + (f':{line}' if line else '') + (f' ({step})' if step else '')
            md.append(f'- **修改落点**: ✓ {loc}')
            md.append(f"- **理由**: {a.get('rationale', '—')}")
            md.append(f"- **影响指标**: `{a.get('expected_impact_metric', '—')}` {a.get('expected_direction', '')}")
            md.append(f"- **关联 finding**: `{a.get('finding_id', '—')}` / hypothesis `{a.get('hypothesis_id', '—')}` ({a.get('hypothesis_category', '')})")
            md.append(f"- **证据 handles**: {', '.join(a.get('evidence_handles', [])) or '—'}")
            sup = a.get('supporting_evidence') or []
            con = a.get('contradicting_evidence') or []
            notes = a.get('verifier_notes') or []
            if sup:
                md.append('- **支持证据**:')
                for s in sup:
                    md.append(f'  - {s}')
            if con:
                md.append('- **反向证据**:')
                for c in con:
                    md.append(f'  - {c}')
            if notes:
                md.append('- **验证备注**:')
                for n in notes:
                    md.append(f'  - {n}')
    if out_scope:
        md.append('\n## 待澄清/超出 code_map 的建议（仅供参考，不直接执行）')
        md.append('| 标题 | 修改方向 | 警告 | 影响指标 |')
        md.append('| :--- | :--- | :--- | :--- |')
        for a in out_scope:
            metric = a.get('expected_impact_metric', '')
            direction = a.get('expected_direction', '')
            impact = f'`{metric}` {direction}' if metric else '—'
            md.append(f"| **{_esc(_action_title(a))}** | {_esc(_action_change(a))} | ⚠ {_esc(a.get('code_map_warning') or '不在 code_map')} | {impact} |")
    md.append('\n## 已确认假设')
    findings = [f for f in data.get('findings', []) or [] if f.get('verdict') == 'confirmed' and f.get('critic_status') == 'approved']
    if not findings:
        md.append('_暂无已 critic 通过的 confirmed finding。_')
    else:
        md.append('| Finding | Hypothesis | Claim | 置信度 | 证据 |')
        md.append('| :--- | :--- | :--- | :--- | :--- |')
        for f in findings:
            md.append(f"| `{f.get('id')}` | `{f.get('hypothesis_id')}` | {_esc(f.get('claim'))} | {int(coerce_confidence(f.get('confidence'), 0.0) * 100)}% | {', '.join(f.get('evidence_handles', [])) or '—'} |")
    gaps = data.get('open_gaps', []) or []
    if gaps:
        md.append('\n## 待回答问题')
        for g in gaps:
            md.append(f'- {g}')
    if guidance:
        md.append('\n## 全局指引')
        md.append(guidance)
    flow = data.get('flow_analysis') or {}
    critical = ', '.join((f'`{s}`' for s in flow.get('critical_steps', [])))
    if critical or flow.get('transition_analysis'):
        md.append('\n## 链路关键节点')
        if critical:
            md.append(f'* **高风险节点**：{critical}')
        for t in flow.get('transition_analysis', []) or []:
            if t.get('type') and t['type'] != 'stable':
                md.append(f"* **{t.get('from_step', '')} → {t.get('to_step', '')}**：{t['type']} (熵变 {t.get('entropy_change')})")
    return '\n'.join(md)
