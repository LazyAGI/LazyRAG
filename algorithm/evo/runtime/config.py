from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from evo.runtime.code_config import CodeAccessConfig, load_code_access


@dataclass(frozen=True)
class ModelGovernanceConfig:
    rate_limit_per_sec: float = 10.0
    burst: int = 15
    cache_size: int = 128
    max_retries: int = 3
    retry_base_seconds: float = 1.0
    use_cache: bool = True
    on_failure: Literal['raise', 'disable'] = 'raise'
    producer_timeout_s: float = 300.0   # cap each producer call; 0 disables
    http_timeout_s: int = 60            # poked onto online lazyllm models via ._timeout; 0 = leave default


def _default_llm_governance() -> ModelGovernanceConfig:
    return ModelGovernanceConfig(on_failure='raise')


def _default_embed_governance() -> ModelGovernanceConfig:
    # Embed is optional: degrade silently after a few transient failures.
    return ModelGovernanceConfig(
        rate_limit_per_sec=20.0,
        burst=30,
        cache_size=512,
        max_retries=3,
        retry_base_seconds=2.0,
        on_failure='disable',
    )


@dataclass(frozen=True)
class AnalysisConfig:
    badcase_score_field: str = 'answer_correctness'
    cluster_method: str = 'hdbscan'
    cluster_min_size: int | None = None


@dataclass(frozen=True)
class EvoConfig:
    data_dir: Path
    output_dir: Path
    default_judge_path: Path
    default_trace_path: Path
    code_access: CodeAccessConfig = field(default_factory=CodeAccessConfig)
    analysis: AnalysisConfig = field(default_factory=AnalysisConfig)
    llm: ModelGovernanceConfig = field(default_factory=_default_llm_governance)
    embed: ModelGovernanceConfig = field(default_factory=_default_embed_governance)

    @property
    def badcase_score_field(self) -> str:
        return self.analysis.badcase_score_field

    @property
    def cluster_method(self) -> str:
        return self.analysis.cluster_method

    @property
    def cluster_min_size(self) -> int | None:
        return self.analysis.cluster_min_size


def load_config(
    *,
    data_dir: Path | None = None,
    output_dir: Path | None = None,
    badcase_score_field: str | None = None,
    code_map_path: Path | None = None,
) -> EvoConfig:
    evo_root = Path(__file__).resolve().parent.parent

    data_dir = Path(data_dir or os.getenv('EVO_DATA_DIR', str(evo_root / 'data')))
    output_dir = Path(output_dir or os.getenv('EVO_OUTPUT_DIR', str(evo_root / 'output')))
    score_field = badcase_score_field or os.getenv('EVO_BADCASE_SCORE_FIELD', 'answer_correctness')

    if code_map_path is None:
        env_cm = os.getenv('EVO_CODE_MAP')
        code_map_path = Path(env_cm) if env_cm else None
    code_access = load_code_access(code_map_path)

    eval_file = os.getenv('EVO_EVAL_FILE', '')
    judge_path = Path(eval_file) if eval_file else data_dir / 'eval_mock.json'

    return EvoConfig(
        data_dir=data_dir,
        output_dir=output_dir,
        default_judge_path=judge_path,
        default_trace_path=data_dir / 'trace_mock.json',
        code_access=code_access,
        analysis=AnalysisConfig(badcase_score_field=score_field),
    )
