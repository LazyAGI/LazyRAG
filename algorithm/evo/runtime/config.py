"""Application configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class EvoConfig:
    data_dir: Path
    output_dir: Path
    default_judge_path: Path
    default_trace_path: Path
    badcase_score_field: str
    model_name: str
    code_map_path: Path | None
    cluster_method: str = "hdbscan"
    cluster_min_size: int | None = None
    cluster_max_k: int = 30
    extra: dict[str, Any] = field(default_factory=dict)


def load_config(
    *,
    data_dir: Path | None = None,
    output_dir: Path | None = None,
    model_name: str | None = None,
    badcase_score_field: str | None = None,
    code_map_path: Path | None = None,
    extra: dict[str, Any] | None = None,
) -> EvoConfig:
    evo_root = Path(__file__).resolve().parent.parent

    data_dir = data_dir or Path(os.getenv("EVO_DATA_DIR", str(evo_root / "data")))
    output_dir = output_dir or Path(os.getenv("EVO_OUTPUT_DIR", str(evo_root / "output")))
    model_name = model_name or os.getenv("EVO_MODEL_NAME", "gpt-3.5-turbo")
    badcase_score_field = badcase_score_field or os.getenv("EVO_BADCASE_SCORE_FIELD", "answer_correctness")

    if code_map_path is None:
        env_cm = os.getenv("EVO_CODE_MAP")
        code_map_path = Path(env_cm) if env_cm else None

    resolved_extra: dict[str, Any] = extra or {}
    if code_map_path and Path(code_map_path).is_file():
        import json
        with open(code_map_path, "r", encoding="utf-8") as f:
            resolved_extra["code_map"] = json.load(f)

    eval_file = os.getenv("EVO_EVAL_FILE", "")
    judge_path = Path(eval_file) if eval_file else Path(data_dir) / "eval_mock.json"

    return EvoConfig(
        data_dir=Path(data_dir),
        output_dir=Path(output_dir),
        default_judge_path=judge_path,
        default_trace_path=Path(data_dir) / "trace_mock.json",
        badcase_score_field=badcase_score_field,
        model_name=model_name,
        code_map_path=code_map_path,
        extra=resolved_extra,
    )
