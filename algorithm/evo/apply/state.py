from __future__ import annotations

import copy
import json
import threading
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from evo.apply.errors import ApplyError


APPLY_STATE_VERSION = 1

RoundPhase = Literal['init', 'opencode_done', 'diff_done', 'tests_done', 'completed']
ApplyStatus = Literal['pending', 'running', 'succeeded', 'failed']

_ROUND_FIELDS = frozenset({
    'phase', 'test_passed', 'files_changed', 'error',
    'started_at', 'finished_at',
})


@dataclass
class RoundState:
    index: int
    phase: RoundPhase = 'init'
    test_passed: bool | None = None
    files_changed: list[str] = field(default_factory=list)
    error: dict | None = None
    started_at: str = ''
    finished_at: str | None = None


@dataclass
class ApplyState:
    schema_version: int = APPLY_STATE_VERSION
    apply_id: str = ''
    repo_root: str = ''
    chat_relpath: str = 'algorithm/chat'
    baseline_dir: str = ''
    report_path: str = ''
    report_digest: str = ''
    allowlist: list[str] = field(default_factory=list)
    max_rounds: int = 3
    current_round: int = 0
    status: ApplyStatus = 'pending'
    rounds: list[RoundState] = field(default_factory=list)


class ApplyStateStore:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        if self._path.exists():
            self._state = self._load()
        else:
            self._state = ApplyState()
            self._save_unlocked()

    @property
    def path(self) -> Path:
        return self._path

    @property
    def state(self) -> ApplyState:
        with self._lock:
            return copy.deepcopy(self._state)

    def initialize(self, *, apply_id: str, repo_root: Path, chat_relpath: str,
                   baseline_dir: Path, report_path: str, report_digest: str,
                   allowlist: Sequence[str], max_rounds: int) -> None:
        with self._lock:
            self._state = ApplyState(
                apply_id=apply_id,
                repo_root=str(repo_root),
                chat_relpath=chat_relpath,
                baseline_dir=str(baseline_dir),
                report_path=report_path,
                report_digest=report_digest,
                allowlist=list(allowlist),
                max_rounds=max_rounds,
                status='pending',
            )
            self._save_unlocked()

    def set_status(self, status: ApplyStatus) -> None:
        with self._lock:
            self._state.status = status
            self._save_unlocked()

    def set_max_rounds(self, n: int) -> None:
        with self._lock:
            self._state.max_rounds = n
            self._save_unlocked()

    def append_round(self, round_state: RoundState) -> None:
        with self._lock:
            self._state.rounds.append(round_state)
            self._state.current_round = round_state.index
            self._save_unlocked()

    def pop_pending_round(self) -> RoundState | None:
        with self._lock:
            if not self._state.rounds:
                return None
            popped = self._state.rounds.pop()
            self._state.current_round = max(0, self._state.current_round - 1)
            self._save_unlocked()
            return popped

    def update_round(self, idx: int, **fields: Any) -> RoundState:
        invalid = set(fields) - _ROUND_FIELDS
        if invalid:
            raise ValueError(f'invalid round fields: {sorted(invalid)}')
        with self._lock:
            if idx < 1 or idx > len(self._state.rounds):
                raise ValueError(f'no round with index {idx}')
            round_obj = self._state.rounds[idx - 1]
            if round_obj.index != idx:
                raise ValueError(
                    f'state drift: rounds[{idx - 1}].index={round_obj.index}, expected {idx}'
                )
            for k, v in fields.items():
                setattr(round_obj, k, v)
            self._save_unlocked()
            return round_obj

    def _load(self) -> ApplyState:
        data = json.loads(self._path.read_text(encoding='utf-8'))
        version = data.get('schema_version')
        if version != APPLY_STATE_VERSION:
            raise ApplyError(
                'STATE_DRIFT', 'apply_state schema_version mismatch',
                {'path': str(self._path), 'expected': APPLY_STATE_VERSION,
                 'actual': version},
            )
        rounds = [RoundState(**r) for r in data.get('rounds', [])]
        return ApplyState(
            schema_version=version,
            apply_id=data.get('apply_id', ''),
            repo_root=data.get('repo_root', ''),
            chat_relpath=data.get('chat_relpath', 'algorithm/chat'),
            baseline_dir=data.get('baseline_dir', ''),
            report_path=data.get('report_path', ''),
            report_digest=data.get('report_digest', ''),
            allowlist=list(data.get('allowlist', []) or []),
            max_rounds=data.get('max_rounds', 3),
            current_round=data.get('current_round', 0),
            status=data.get('status', 'pending'),
            rounds=rounds,
        )

    def _save_unlocked(self) -> None:
        tmp = self._path.with_suffix(self._path.suffix + '.tmp')
        tmp.write_text(
            json.dumps(asdict(self._state), ensure_ascii=False, indent=2),
            encoding='utf-8',
        )
        tmp.replace(self._path)
