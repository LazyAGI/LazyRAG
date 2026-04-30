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
    producer_timeout_s: float = 600.0
    http_timeout_s: int = 300


def _default_llm_governance() -> ModelGovernanceConfig:
    return ModelGovernanceConfig(
        on_failure='raise',
        http_timeout_s=int(os.getenv('EVO_LLM_HTTP_TIMEOUT_S', '300')),
        producer_timeout_s=float(os.getenv('EVO_LLM_PRODUCER_TIMEOUT_S', '600')),
    )


def _default_embed_governance() -> ModelGovernanceConfig:
    return ModelGovernanceConfig(
        rate_limit_per_sec=20.0,
        burst=30,
        cache_size=512,
        max_retries=3,
        retry_base_seconds=2.0,
        on_failure='disable',
        http_timeout_s=int(os.getenv('EVO_EMBED_HTTP_TIMEOUT_S', '60')),
        producer_timeout_s=float(os.getenv('EVO_EMBED_PRODUCER_TIMEOUT_S', '120')),
    )


@dataclass(frozen=True)
class AnalysisConfig:
    badcase_score_field: str = 'answer_correctness'
    cluster_method: str = 'hdbscan'
    cluster_min_size: int | None = None
    enable_embed_features: bool = False


@dataclass(frozen=True)
class EvoModelConfig:
    llm_role: str = 'evo_llm'
    embed_role: str = 'evo_embed'
    auto_user_role: str = 'evo_llm'


@dataclass(frozen=True)
class StorageConfig:
    base_dir: Path

    @property
    def work_dir(self) -> Path:
        return self.base_dir / 'work'

    @property
    def runs_dir(self) -> Path:
        return self.work_dir / 'runs'

    @property
    def applies_dir(self) -> Path:
        return self.work_dir / 'applies'

    @property
    def reports_dir(self) -> Path:
        return self.work_dir / 'reports'

    @property
    def diffs_dir(self) -> Path:
        return self.work_dir / 'diffs'

    @property
    def opencode_dir(self) -> Path:
        return self.work_dir / 'opencode'

    @property
    def git_dir(self) -> Path:
        return self.work_dir / 'git'

    @property
    def state_db_path(self) -> Path:
        return self.base_dir / 'state'

    def ensure(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class DatasetGenConfig:
    kb_base_url: str = 'http://localhost:8055'
    chunk_base_url: str = 'http://localhost:8055'
    max_workers: int = 5
    task_settings: dict = field(
        default_factory=lambda: {
            'single_hop': {'num': 10},
            'multi_hop': {'num': 10},
            'table': {'num': 10},
            'list': {'num': 10},
        }
    )


@dataclass(frozen=True)
class EvalRunConfig:
    provider: str = ''
    base_url: str = ''
    token: str = ''
    mock_path: str = ''


@dataclass(frozen=True)
class EvoConfig:
    data_dir: Path
    storage: StorageConfig
    default_judge_path: Path
    default_trace_path: Path
    chat_source: Path = Path('/app/algorithm/chat')
    code_access: CodeAccessConfig = field(default_factory=CodeAccessConfig)
    analysis: AnalysisConfig = field(default_factory=AnalysisConfig)
    llm: ModelGovernanceConfig = field(default_factory=_default_llm_governance)
    embed: ModelGovernanceConfig = field(default_factory=_default_embed_governance)
    model_config: EvoModelConfig = field(default_factory=EvoModelConfig)
    dataset_gen: DatasetGenConfig = field(default_factory=DatasetGenConfig)
    eval_run: EvalRunConfig = field(default_factory=EvalRunConfig)
    profile: str = 'dev'

    @property
    def badcase_score_field(self) -> str:
        return self.analysis.badcase_score_field

    @property
    def cluster_method(self) -> str:
        return self.analysis.cluster_method

    @property
    def cluster_min_size(self) -> int | None:
        return self.analysis.cluster_min_size

    @property
    def enable_embed_features(self) -> bool:
        return self.analysis.enable_embed_features


def load_config(
    *,
    data_dir: Path | None = None,
    base_dir: Path | None = None,
    badcase_score_field: str | None = None,
    code_map_path: Path | None = None,
) -> EvoConfig:
    evo_root = Path(__file__).resolve().parent.parent
    project_root = evo_root.parent
    data_dir = Path(data_dir or os.getenv('EVO_DATA_DIR', str(evo_root / 'data')))
    base_dir = Path(base_dir or os.getenv('EVO_BASE_DIR', str(project_root / 'data' / 'evo')))
    score_field = badcase_score_field or os.getenv('EVO_BADCASE_SCORE_FIELD', 'answer_correctness')
    if code_map_path is None:
        env_cm = os.getenv('EVO_CODE_MAP')
        code_map_path = Path(env_cm) if env_cm else None
    code_access = load_code_access(code_map_path)
    eval_file = os.getenv('EVO_EVAL_FILE', '')
    judge_path = Path(eval_file) if eval_file else data_dir / 'eval_mock.json'
    model_config = EvoModelConfig(
        llm_role=os.getenv('EVO_LLM_ROLE', 'evo_llm'),
        embed_role=os.getenv('EVO_EMBED_ROLE', 'evo_embed'),
        auto_user_role=os.getenv('EVO_AUTO_USER_ROLE', 'evo_llm'),
    )
    storage = StorageConfig(base_dir=base_dir)
    storage.ensure()
    analysis = AnalysisConfig(
        badcase_score_field=score_field,
        enable_embed_features=os.getenv('EVO_ANALYSIS_ENABLE_EMBED_FEATURES', '').lower() in {'1', 'true', 'yes', 'on'},
    )
    chat_source = Path(os.getenv('EVO_CHAT_SOURCE', str(project_root / 'algorithm' / 'chat')))
    dataset_gen = DatasetGenConfig(
        kb_base_url=os.getenv('EVO_KB_BASE_URL', 'http://localhost:8055'),
        chunk_base_url=os.getenv('EVO_CHUNK_BASE_URL', 'http://localhost:8055'),
        max_workers=int(os.getenv('EVO_DATASETGEN_MAX_WORKERS', '5')),
    )
    eval_run = EvalRunConfig(
        provider=os.getenv('EVO_EVAL_PROVIDER', ''),
        base_url=os.getenv('EVO_EVAL_BASE_URL', ''),
        token=os.getenv('EVO_EVAL_TOKEN', ''),
        mock_path=os.getenv('EVO_EVAL_MOCK_PATH', ''),
    )
    profile = os.getenv('EVO_PROFILE', 'dev')
    cfg = EvoConfig(
        data_dir=data_dir,
        storage=storage,
        default_judge_path=judge_path,
        default_trace_path=data_dir / 'trace_mock.json',
        chat_source=chat_source,
        code_access=code_access,
        analysis=analysis,
        model_config=model_config,
        dataset_gen=dataset_gen,
        eval_run=eval_run,
        profile=profile,
    )
    if profile == 'prod':
        missing = []
        if not os.getenv('EVO_EVAL_PROVIDER'):
            missing.append('EVO_EVAL_PROVIDER')
        if not os.getenv('EVO_TRACE_PROVIDER'):
            missing.append('EVO_TRACE_PROVIDER')
        if not os.getenv('EVO_CHAT_SOURCE'):
            missing.append('EVO_CHAT_SOURCE')
        if missing:
            raise RuntimeError(f"EVO_PROFILE=prod missing required env vars: {', '.join(missing)}")
        storage.ensure()
    return cfg
