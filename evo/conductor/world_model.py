from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Literal

WORLD_MODEL_VERSION = 1

Status = Literal["initializing", "investigating", "synthesizing", "converged", "aborted"]
HypothesisStatus = Literal[
    "proposed", "investigating", "confirmed", "refuted", "inconclusive",
]
Verdict = Literal["confirmed", "refuted", "inconclusive"]
CriticStatus = Literal["pending", "approved", "needs_revision"]


@dataclass
class Hypothesis:
    id: str
    claim: str
    category: str = ""
    status: HypothesisStatus = "proposed"
    confidence: float = 0.0
    evidence_handles: list[str] = field(default_factory=list)
    investigation_paths: list[str] = field(default_factory=list)
    source: str = ""


@dataclass
class Finding:
    id: str
    hypothesis_id: str
    claim: str
    verdict: Verdict
    confidence: float = 0.0
    evidence_handles: list[str] = field(default_factory=list)
    critic_status: CriticStatus = "pending"
    critic_notes: list[str] = field(default_factory=list)
    suggested_action: str = ""


@dataclass
class WorldModel:
    run_id: str
    version: int = WORLD_MODEL_VERSION
    iteration: int = 0
    status: Status = "initializing"
    hypotheses: list[Hypothesis] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)


class WorldModelStore:
    """Persistent JSON state for one diagnostic run; atomic writes + lock."""

    def __init__(self, path: Path, run_id: str) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._world = self._load() if self._path.exists() else WorldModel(run_id=run_id)
        if self._world.run_id != run_id:
            self._world = WorldModel(run_id=run_id)
        self._save()

    @property
    def path(self) -> Path:
        return self._path

    @property
    def world(self) -> WorldModel:
        return self._world

    def update(self, fn: Callable[[WorldModel], None]) -> None:
        with self._lock:
            fn(self._world)
            self._save()

    def _load(self) -> WorldModel:
        data = json.loads(self._path.read_text(encoding="utf-8"))
        return WorldModel(
            run_id=data["run_id"],
            version=data.get("version", WORLD_MODEL_VERSION),
            iteration=data.get("iteration", 0),
            status=data.get("status", "initializing"),
            hypotheses=[Hypothesis(**h) for h in data.get("hypotheses", [])],
            findings=[Finding(**f) for f in data.get("findings", [])],
            open_questions=list(data.get("open_questions", [])),
        )

    def _save(self) -> None:
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(asdict(self._world), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self._path)
