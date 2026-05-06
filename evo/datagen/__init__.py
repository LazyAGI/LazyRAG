from __future__ import annotations
import logging
from typing import Any
from evo.datagen.evaluate import create_evaluate_task
from evo.datagen.metrics import calculate_metrics
from evo.datagen.prompts import prompt_evaluate, prompt_generate_single_hop
from evo.datagen.queue import get_eval_queue
from evo.datagen.single_hop import generate_single_hop, generate_single_hop_from_chunks
from evo.datagen.corpus import build_corpus_index
from evo.datagen.multi_hop import generate_multi_hop_from_chunks
from evo.datagen.structured import generate_list_questions, generate_table_questions
from evo.datagen.validate import safe_parse_qa_json
from evo.datagen.writer import (
    build_eval_report,
    build_full_eval_set,
    ensure_eval_dir,
    extract_json,
    load_report,
    save_eval_report,
    write_full_eval_set,
)
from evo.datagen.kb_client import KBClient
from evo.datagen.langfuse import fetch_traces_for_report
from evo.runtime.config import EvoConfig
from evo.runtime.fs import atomic_write_json

_log = logging.getLogger('evo.datagen')


class DatasetGenerationEmptyError(RuntimeError):
    code = 'DATASET_EMPTY'
    kind = 'permanent'


class KBDocsEmptyError(RuntimeError):
    code = 'KB_DOCS_EMPTY'
    kind = 'permanent'


class KBChunksEmptyError(RuntimeError):
    code = 'KB_CHUNKS_EMPTY'
    kind = 'permanent'


class EvalDatasetEmptyError(RuntimeError):
    code = 'EVAL_DATASET_EMPTY'
    kind = 'permanent'


__all__ = [
    'run_generate_pipeline',
    'run_eval',
    'load_report',
    'fetch_traces_for_report',
    'generate_single_hop',
    'create_evaluate_task',
    'get_eval_queue',
    'calculate_metrics',
    'build_eval_report',
    'build_full_eval_set',
    'save_eval_report',
    'write_full_eval_set',
    'load_report',
    'ensure_eval_dir',
    'extract_json',
    'safe_parse_qa_json',
    'prompt_generate_single_hop',
    'prompt_evaluate',
    'KBClient',
    'fetch_traces_for_report',
]
_TYPE_ORDER = ('single_hop', 'multi_hop', 'table', 'list')
_TYPE_TO_QUESTION_TYPE = {'single_hop': 1, 'multi_hop': 2, 'table': 4, 'list': 5}


def run_generate_pipeline(
    kb_id: str,
    algo_id: str,
    eval_name: str,
    *,
    dataset_source: KBClient,
    config: EvoConfig,
    thread_id: str | None = None,
    llm_factory=None,
    cancel=None,
    num_cases: int | None = None,
    on_progress=None,
) -> tuple[str, dict[str, Any]]:
    _log.info('start dataset_gen kb_id=%s algo_id=%s eval_name=%s', kb_id, algo_id, eval_name)
    _check_cancel(cancel)
    docs = _get_docs_or_raise(dataset_source, kb_id, algo_id)
    _check_cancel(cancel)
    plan = _generation_plan(num_cases, config.dataset_gen.task_settings)
    result: list[dict[str, Any]] = []
    stats: dict[str, int] = {}
    target_count = sum(plan.values())

    def add(kind: str, items: list[dict]) -> None:
        result.extend(items)
        stats[kind] = stats.get(kind, 0) + len(items)
        if on_progress:
            on_progress(min(len(result), target_count), target_count)

    workers = max(1, min(config.dataset_gen.max_workers, 8))
    corpus = build_corpus_index(
        dataset_source,
        kb_id,
        algo_id,
        cache_dir=config.storage.work_dir / 'datagen_cache',
        docs=docs,
        max_workers=workers,
    )
    _check_cancel(cancel)
    if not corpus.chunks:
        raise KBChunksEmptyError(
            f'no chunks found for kb_id={kb_id} algo_id={algo_id}; '
            'ensure document chunk API is populated or mount LAZYRAG_UPLOAD_HOST_DIR'
        )
    if plan['single_hop'] > 0:
        add(
            'single_hop',
            generate_single_hop_from_chunks(
                corpus.chunks, count=plan['single_hop'], max_workers=workers, llm_factory=llm_factory
            ),
        )
    _check_cancel(cancel)
    if plan['multi_hop'] > 0:
        add(
            'multi_hop',
            generate_multi_hop_from_chunks(
                corpus.chunks, count=plan['multi_hop'], max_workers=workers, llm_factory=llm_factory
            ),
        )
    _check_cancel(cancel)
    if plan['table'] > 0:
        add(
            'table',
            generate_table_questions(corpus.chunks, count=plan['table'], max_workers=workers, llm_factory=llm_factory),
        )
    _check_cancel(cancel)
    if plan['list'] > 0:
        add(
            'list',
            generate_list_questions(corpus.chunks, count=plan['list'], max_workers=workers, llm_factory=llm_factory),
        )
    missing = target_count - len(result)
    if missing > 0:
        _log.info('dataset_gen shortfall=%s; filling with single-hop', missing)
        add(
            'single_hop',
            generate_single_hop(
                dataset_source, kb_id, algo_id, count=missing, max_workers=workers, llm_factory=llm_factory
            ),
        )
    final_data = build_full_eval_set(result[:target_count], eval_name=eval_name, kb_id=kb_id)
    final_data['generation_plan'] = plan
    final_data['question_type_counts'] = _question_type_counts(final_data.get('cases', []))
    final_data['generation_stats'] = stats
    cases = final_data.get('cases', [])
    if not cases:
        raise DatasetGenerationEmptyError(f'dataset generation produced no cases for {eval_name}')
    if target_count and len(cases) < target_count:
        raise DatasetGenerationEmptyError(
            f'dataset generation produced {len(cases)}/{target_count} valid cases for {eval_name}'
        )
    path = config.storage.base_dir / 'datasets' / eval_name / 'eval_data.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, final_data)
    _log.info('dataset_gen finished %s cases -> %s', len(final_data.get('cases', [])), path)
    return (str(path), final_data)


def _generation_plan(num_cases: int | None, settings: dict) -> dict[str, int]:
    if num_cases is None:
        return {k: int((settings.get(k) or {}).get('num', 0)) for k in _TYPE_ORDER}
    total = num_cases
    if total <= 0:
        total = 40
    base, rem = divmod(total, len(_TYPE_ORDER))
    plan = {k: base for k in _TYPE_ORDER}
    for k in _TYPE_ORDER[:rem]:
        plan[k] += 1
    return plan


def _question_type_counts(cases: list[dict]) -> dict[str, int]:
    out = {k: 0 for k in _TYPE_ORDER}
    by_code = {v: k for (k, v) in _TYPE_TO_QUESTION_TYPE.items()}
    for case in cases:
        key = by_code.get(case.get('question_type'), 'unknown')
        out[key] = out.get(key, 0) + 1
    return out


def _check_cancel(cancel) -> None:
    if cancel and cancel():
        from evo.service.core.errors import StateError

        raise StateError('TASK_CANCELLED', 'dataset generation cancelled')


def _get_docs_or_raise(dataset_source: KBClient, kb_id: str, algo_id: str) -> list[dict]:
    docs = dataset_source.get_doc_list(kb_id, algo_id)
    if docs:
        return docs
    hint = ''
    if ',' in kb_id and kb_id.split(',', 1)[0].startswith(('http://', 'https://')):
        hint = (
            ' URL_MAP document_url datasets are not enumerable through /v1/docs; '
            'use a local ds_* kb_id or add a remote enumeration adapter.'
        )
    raise KBDocsEmptyError(f'no docs found for kb_id={kb_id} algo_id={algo_id}.{hint}')


def run_eval(
    dataset_id: str,
    target_chat_url: str,
    *,
    cfg: EvoConfig,
    llm_factory=None,
    max_workers: int = 10,
    dataset_name: str = '',
    filters: dict[str, Any] | None = None,
    require_trace: bool = True,
    persist_report: bool = True,
    on_progress=None,
    on_judge_progress=None,
) -> dict[str, Any]:
    _log.info('start eval dataset_id=%s target=%s', dataset_id, target_chat_url)
    eval_data = get_eval_queue(
        dataset_id,
        dataset_name=dataset_name,
        base_dir=cfg.storage.base_dir,
        target_chat_url=target_chat_url,
        max_workers=max_workers,
        filters=filters or {},
        require_trace=require_trace,
        on_progress=on_progress,
    )
    eval_queue = eval_data['eval_queue']
    if not eval_queue:
        raise EvalDatasetEmptyError(f'eval dataset {dataset_id} has no cases')
    result = create_evaluate_task(
        eval_queue, llm_factory=llm_factory, max_workers=max_workers, on_progress=on_judge_progress
    )
    report = build_eval_report(result, eval_data)
    if persist_report:
        path = save_eval_report(dataset_id, report, cfg.storage.base_dir)
        _log.info('eval %s done -> %s', dataset_id, path)
    else:
        _log.info('eval %s done', dataset_id)
    return report
