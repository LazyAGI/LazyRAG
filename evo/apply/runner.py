from __future__ import annotations

import hashlib
import json
import logging
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from evo.apply import opencode as oc
from evo.apply.errors import ApplyError
from evo.apply.state import ApplyStateStore, RoundState
from evo.apply.tests import TestOutcome, run_tests
from evo.apply.workspace import compute_diff, snapshot_chat
from evo.runtime.config import EvoConfig
from evo.utils import safe_under


_NO_CHANGES_FEEDBACK = (
    '上一轮 opencode 未对任何 allowlist 中的文件做出修改。'
    '本轮必须实际改动至少一个允许文件，否则任务无法收尾。'
)

log = logging.getLogger('evo.apply')


@dataclass
class ApplyResult:
    apply_id: str
    apply_dir: str
    status: Literal['SUCCEEDED', 'FAILED']
    rounds: list[dict] = field(default_factory=list)
    final_diff_path: str | None = None
    final_test_log_path: str | None = None
    error: dict | None = None


def run_apply(
    report: Any,
    *,
    config: EvoConfig,
    repo_root: Path | None = None,
    chat_relpath: str = 'algorithm/chat',
    max_rounds: int = 3,
    test_command: tuple[str, ...] = ('bash', 'tests/run-all.sh'),
    instruction: str = '根据 report 完成代码修改',
    opencode_options: oc.OpencodeOptions | None = None,
) -> ApplyResult:
    _, report_dict, report_origin = _coerce_report(report)
    in_scope_actions = _filter_in_scope_actions(report_dict)
    if not in_scope_actions:
        raise ApplyError('REPORT_INVALID', 'report has no in-scope actions',
                         {'report_origin': str(report_origin) if report_origin else None})

    repo = _resolve_repo_root(repo_root)
    if not (repo / chat_relpath).resolve().is_dir():
        raise ApplyError('CHAT_DIR_NOT_FOUND', 'chat directory missing under repo_root',
                         {'repo_root': str(repo), 'chat_relpath': chat_relpath})

    allowlist = _build_allowlist(config, repo)
    if not allowlist:
        raise ApplyError('CODE_MAP_EMPTY', 'code_map is empty; nothing is modifiable')

    apply_id = f'apply_{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8]}'
    apply_dir = safe_under(config.output_dir, f'apply/{apply_id}')
    apply_dir.mkdir(parents=True, exist_ok=True)
    log.info('apply start: id=%s repo=%s chat=%s out=%s max_rounds=%d',
             apply_id, repo, chat_relpath, apply_dir, max_rounds)

    canonical_text = json.dumps(report_dict, ensure_ascii=False, indent=2, sort_keys=True)
    digest = hashlib.sha256(canonical_text.encode('utf-8')).hexdigest()
    modification_plan = _build_modification_plan(in_scope_actions, repo)

    (apply_dir / 'input').mkdir(parents=True, exist_ok=True)
    (apply_dir / 'input' / 'report.json').write_text(canonical_text, encoding='utf-8')
    (apply_dir / 'input' / 'modification_plan.json').write_text(
        json.dumps(modification_plan, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )

    baseline_dir = apply_dir / 'baseline'
    snapshot_chat(repo, baseline_dir, chat_relpath)
    log.info('baseline snapshot ready: %s', baseline_dir)

    store = ApplyStateStore(apply_dir / 'apply_state.json')
    store.initialize(
        apply_id=apply_id,
        repo_root=repo,
        chat_relpath=chat_relpath,
        baseline_dir=baseline_dir,
        report_path=str(report_origin) if report_origin else str(apply_dir / 'input' / 'report.json'),
        report_digest=digest,
        allowlist=allowlist,
        max_rounds=max_rounds,
    )

    return _run_loop(
        store=store, apply_dir=apply_dir, repo=repo, chat_relpath=chat_relpath,
        baseline_dir=baseline_dir, modification_plan=modification_plan,
        allowlist=allowlist, instruction=instruction, test_command=test_command,
        options=opencode_options or oc.OpencodeOptions(),
        prior_failure='',
    )


def resume_apply(apply_dir: Path, *, max_rounds: int | None = None,
                 test_command: tuple[str, ...] | None = None,
                 instruction: str | None = None,
                 opencode_options: oc.OpencodeOptions | None = None) -> ApplyResult:
    apply_dir = Path(apply_dir).resolve()
    state_path = apply_dir / 'apply_state.json'
    report_path = apply_dir / 'input' / 'report.json'
    plan_path = apply_dir / 'input' / 'modification_plan.json'
    if not state_path.is_file() or not report_path.is_file() or not plan_path.is_file():
        raise ApplyError('STATE_DRIFT', 'apply_dir missing required files',
                         {'apply_dir': str(apply_dir)})

    canonical_text = report_path.read_text(encoding='utf-8')
    digest = hashlib.sha256(canonical_text.encode('utf-8')).hexdigest()

    store = ApplyStateStore(state_path)
    if store.state.report_digest != digest:
        raise ApplyError('STATE_DRIFT', 'report digest mismatch; refuse to resume',
                         {'expected': store.state.report_digest, 'actual': digest})
    log.info('resume apply: dir=%s last_round=%d max_rounds=%d',
             apply_dir, store.state.current_round, store.state.max_rounds)

    if max_rounds is not None:
        store.set_max_rounds(max_rounds)

    snap = store.state
    repo = Path(snap.repo_root)
    chat_relpath = snap.chat_relpath
    baseline_dir = Path(snap.baseline_dir)
    modification_plan = json.loads(plan_path.read_text(encoding='utf-8'))
    allowlist = list(snap.allowlist)

    last_round = snap.rounds[-1] if snap.rounds else None
    if last_round and last_round.phase == 'completed' and last_round.test_passed:
        return _build_result(store, apply_dir, status='SUCCEEDED')

    prior_failure = ''
    if last_round and last_round.phase == 'completed' and last_round.test_passed is False:
        prior_failure = _load_prior_failure(apply_dir, last_round)
    elif last_round and last_round.phase != 'completed':
        # State first; defensive cleanup happens when round_dir is recreated below.
        store.pop_pending_round()
        log.info('resume: dropped pending round_%03d (was phase=%s)',
                 last_round.index, last_round.phase)

    return _run_loop(
        store=store, apply_dir=apply_dir, repo=repo, chat_relpath=chat_relpath,
        baseline_dir=baseline_dir, modification_plan=modification_plan,
        allowlist=allowlist,
        instruction=instruction or '根据 report 继续完成代码修改',
        test_command=test_command or ('bash', 'tests/run-all.sh'),
        options=opencode_options or oc.OpencodeOptions(),
        prior_failure=prior_failure,
    )


def _run_loop(
    *, store: ApplyStateStore, apply_dir: Path, repo: Path, chat_relpath: str,
    baseline_dir: Path, modification_plan: list[dict], allowlist: list[str],
    instruction: str, test_command: tuple[str, ...],
    options: oc.OpencodeOptions, prior_failure: str,
) -> ApplyResult:
    binary = oc.preflight(options.binary)
    log.info('opencode preflight ok: binary=%s', binary)
    store.set_status('running')

    last_diff_path: Path | None = None
    last_test_log: Path | None = None
    final_error: dict | None = None
    final_status: Literal['SUCCEEDED', 'FAILED'] = 'FAILED'

    start_index = store.state.current_round + 1
    max_rounds = store.state.max_rounds
    for i in range(start_index, max_rounds + 1):
        round_dir = apply_dir / 'rounds' / f'round_{i:03d}'
        if round_dir.exists():
            shutil.rmtree(round_dir)
        (round_dir / 'input').mkdir(parents=True, exist_ok=True)
        log.info('round %d/%d start', i, max_rounds)

        store.append_round(RoundState(index=i, started_at=_now_iso()))

        prompt = _build_prompt(instruction, modification_plan, allowlist, prior_failure)
        (round_dir / 'input' / 'prompt.txt').write_text(prompt, encoding='utf-8')

        try:
            outcome = oc.run_opencode(prompt, cwd=repo,
                                       artifact_dir=round_dir / 'opencode',
                                       binary=binary, options=options)
        except ApplyError as exc:
            log.error('round %d: opencode raised %s', i, exc.code)
            final_error = exc.to_payload()
            store.update_round(i, phase='completed', error=final_error,
                               finished_at=_now_iso())
            break

        log.info('round %d: opencode returncode=%d text_len=%d',
                 i, outcome.returncode, len(outcome.text_summary))
        if outcome.returncode != 0:
            final_error = {
                'code': 'OPENCODE_RUN_FAILED',
                'message': f'opencode exited with returncode={outcome.returncode}',
                'details': {'last_error': outcome.last_error},
            }
            store.update_round(i, phase='completed', error=final_error,
                               finished_at=_now_iso())
            break
        store.update_round(i, phase='opencode_done')

        try:
            diff = compute_diff(repo, baseline_dir, chat_relpath, round_dir / 'diff')
        except ApplyError as exc:
            log.error('round %d: diff failed %s', i, exc.code)
            final_error = exc.to_payload()
            store.update_round(i, phase='completed', error=final_error,
                               finished_at=_now_iso())
            break
        last_diff_path = diff.unified_diff_path
        log.info('round %d: diff files=%d bytes=%d',
                 i, len(diff.files_changed), diff.byte_count)
        store.update_round(i, phase='diff_done', files_changed=diff.files_changed)

        if not diff.files_changed:
            log.warning('round %d: opencode produced no changes', i)
            store.update_round(i, phase='completed', test_passed=False,
                               error={'code': 'OPENCODE_NO_CHANGES',
                                      'message': 'opencode 本轮未修改任何允许文件',
                                      'details': {}},
                               finished_at=_now_iso())
            prior_failure = _NO_CHANGES_FEEDBACK
            continue

        test_outcome: TestOutcome = run_tests(repo, round_dir / 'tests',
                                               command=test_command)
        last_test_log = test_outcome.log_path
        store.update_round(i, phase='tests_done', test_passed=test_outcome.passed)

        if test_outcome.passed:
            log.info('round %d: tests passed', i)
            final_status = 'SUCCEEDED'
            store.update_round(i, phase='completed', error=None,
                               finished_at=_now_iso())
            break

        log.info('round %d: tests failed (%d failures)', i, len(test_outcome.failed_tests))
        prior_failure = _build_failure_context(diff.files_changed, test_outcome)
        store.update_round(i, phase='completed', error=None,
                           finished_at=_now_iso())
    else:
        final_error = final_error or _exhausted_error(store)

    store.set_status('succeeded' if final_status == 'SUCCEEDED' else 'failed')
    log.info('apply end: status=%s rounds=%d', final_status, len(store.state.rounds))
    return _build_result(
        store, apply_dir, status=final_status,
        final_diff_path=last_diff_path,
        final_test_log_path=last_test_log,
        error=final_error if final_status == 'FAILED' else None,
    )


def _exhausted_error(store: ApplyStateStore) -> dict:
    rounds = store.state.rounds
    last = rounds[-1] if rounds else None
    last_code = (last.error or {}).get('code') if last else None
    if last_code == 'OPENCODE_NO_CHANGES':
        return {
            'code': 'OPENCODE_NO_CHANGES',
            'message': f'opencode 在 {store.state.max_rounds} 轮内均未产生文件变更',
            'details': {'rounds': store.state.max_rounds},
        }
    return {
        'code': 'MAX_ROUNDS_EXCEEDED',
        'message': f'tests still failing after {store.state.max_rounds} round(s)',
        'details': {},
    }


def _load_prior_failure(apply_dir: Path, last_round: RoundState) -> str:
    code = (last_round.error or {}).get('code', '')
    if code == 'OPENCODE_NO_CHANGES':
        return _NO_CHANGES_FEEDBACK
    tb_path = (apply_dir / 'rounds' / f'round_{last_round.index:03d}'
               / 'tests' / 'traceback.md')
    tb = tb_path.read_text(encoding='utf-8') if tb_path.is_file() else ''
    return _build_failure_context_from_text(last_round.files_changed, tb)


def _build_failure_context(files_changed: list[str],
                           test_outcome: TestOutcome) -> str:
    tb = (test_outcome.traceback_md_path.read_text(encoding='utf-8')
          if test_outcome.traceback_md_path else '')
    return _build_failure_context_from_text(files_changed, tb)


def _build_failure_context_from_text(files_changed: list[str], tb_md: str) -> str:
    parts: list[str] = []
    if files_changed:
        parts.append('## 当前相对 baseline 已修改的文件（仍在仓库内，可继续在其上推进或自行回退）')
        parts.extend(f'- {f}' for f in files_changed)
        parts.append('')
    if tb_md.strip():
        parts.append(tb_md.strip())
    return '\n'.join(parts).strip()


def _build_result(store: ApplyStateStore, apply_dir: Path, *,
                  status: Literal['SUCCEEDED', 'FAILED'],
                  final_diff_path: Path | None = None,
                  final_test_log_path: Path | None = None,
                  error: dict | None = None) -> ApplyResult:
    snap = store.state
    result = ApplyResult(
        apply_id=snap.apply_id,
        apply_dir=str(apply_dir),
        status=status,
        rounds=[asdict(r) for r in snap.rounds],
        final_diff_path=str(final_diff_path) if final_diff_path else None,
        final_test_log_path=str(final_test_log_path) if final_test_log_path else None,
        error=error,
    )
    (apply_dir / 'result.json').write_text(
        json.dumps(asdict(result), ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    return result


def _coerce_report(report: Any) -> tuple[Any, dict, Path | None]:
    try:
        from evo.domain.diagnosis import DiagnosisReport
    except ImportError:
        DiagnosisReport = None  # type: ignore[assignment]

    if DiagnosisReport is not None and isinstance(report, DiagnosisReport):
        return report, report.to_dict(), None
    if isinstance(report, dict):
        return None, dict(report), None
    if isinstance(report, (str, Path)):
        path = Path(report).expanduser().resolve()
        if not path.is_file():
            raise ApplyError('REPORT_INVALID', 'report json not found',
                             {'path': str(path)})
        loaded = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(loaded, dict):
            raise ApplyError('REPORT_INVALID', 'report root must be an object',
                             {'path': str(path)})
        return None, loaded, path
    raise ApplyError('REPORT_INVALID', 'unsupported report type',
                     {'type': type(report).__name__})


def _filter_in_scope_actions(report_dict: dict) -> list[dict]:
    actions = report_dict.get('actions') or []
    if not isinstance(actions, list):
        raise ApplyError('REPORT_INVALID', 'report.actions must be a list',
                         {'actual_type': type(actions).__name__})
    return [a for a in actions
            if isinstance(a, dict) and a.get('code_map_in_scope') and a.get('code_map_target')]


def _build_modification_plan(actions: list[dict], repo: Path) -> list[dict]:
    return [{
        'id': str(a.get('id', '')),
        'title': str(a.get('title', '')),
        'rationale': str(a.get('rationale', '')),
        'suggested_changes': str(a.get('suggested_changes', '')),
        'priority': str(a.get('priority', '')),
        'files': [_normalize_target(str(a.get('code_map_target', '')), repo)],
    } for a in actions]


def _normalize_target(target: str, repo: Path) -> str:
    if not target:
        return ''
    p = Path(target)
    if p.is_absolute():
        try:
            return p.resolve().relative_to(repo).as_posix()
        except ValueError:
            return p.as_posix()
    return p.as_posix()


def _build_allowlist(config: EvoConfig, repo: Path) -> list[str]:
    out: set[str] = set()
    for k in config.code_access.code_map.keys():
        if not k:
            continue
        p = Path(k)
        if p.is_absolute():
            try:
                out.add(p.resolve().relative_to(repo).as_posix())
            except ValueError:
                continue
        else:
            out.add(p.as_posix())
    return sorted(out)


def _resolve_repo_root(repo_root: Path | None) -> Path:
    candidate = (Path(repo_root).expanduser().resolve()
                 if repo_root is not None else Path.cwd().resolve())
    if not candidate.is_dir():
        raise ApplyError('REPO_NOT_FOUND', 'repo_root does not exist',
                         {'repo_root': str(candidate)})
    return candidate


def _build_prompt(instruction: str, modification_plan: list[dict],
                  allowlist: list[str], prior_failure: str) -> str:
    parts: list[str] = [instruction.strip(), '']
    parts.append('允许修改的文件（严格遵守，禁止改动其它文件）：')
    parts.extend(f'- {f}' for f in allowlist)
    parts.append('')
    parts.append('修改计划（JSON）：')
    parts.append(json.dumps(modification_plan, ensure_ascii=False, indent=2))
    if prior_failure.strip():
        parts.append('')
        parts.append('上一轮失败上下文（请据此调整本轮修改）：')
        parts.append(prior_failure.strip())
    return '\n'.join(parts) + '\n'


def _now_iso() -> str:
    return datetime.now().isoformat(timespec='seconds')
