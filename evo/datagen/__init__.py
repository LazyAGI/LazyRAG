from __future__ import annotations

import logging
from typing import Any

from evo.datagen.evaluate import create_evaluate_task
from evo.datagen.graph import ParallelKGBuilder
from evo.datagen.metrics import calculate_metrics
from evo.datagen.multi_hop import generate_multi_hop
from evo.datagen.prompts import (
    prompt_evaluate,
    prompt_extract_graph,
    prompt_generate_formula,
    prompt_generate_multihop,
    prompt_generate_single_hop,
    prompt_generate_table,
    prompt_is_real_multihop,
)
from evo.datagen.queue import get_eval_queue
from evo.datagen.llm import chat
from evo.datagen.single_hop import generate_single_hop
from evo.datagen.validate import is_qa_json_valid, safe_parse_qa_json
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


class EvalDatasetEmptyError(RuntimeError):
    code = 'EVAL_DATASET_EMPTY'
    kind = 'permanent'


__all__ = [
    'run_generate_pipeline',
    'run_eval',
    'load_report',
    'fetch_traces_for_report',
    'generate_single_hop',
    'generate_multi_hop',
    'ParallelKGBuilder',
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
    'is_qa_json_valid',
    'safe_parse_qa_json',
    'prompt_generate_single_hop',
    'prompt_generate_table',
    'prompt_generate_formula',
    'prompt_evaluate',
    'prompt_is_real_multihop',
    'prompt_extract_graph',
    'prompt_generate_multihop',
    'KBClient',
    'fetch_traces_for_report',
]


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
) -> tuple[str, dict[str, Any]]:
    _log.info('start dataset_gen kb_id=%s algo_id=%s eval_name=%s',
              kb_id, algo_id, eval_name)
    _check_cancel(cancel)
    docs = _get_docs_or_raise(dataset_source, kb_id, algo_id)
    _check_cancel(cancel)
    count = config.dataset_gen.task_settings.get('single_hop', {}).get('num', 1)
    result = _generate_single_hop_from_kb(
        dataset_source, docs, kb_id, algo_id, count=count, llm_factory=llm_factory)
    if not result:
        result = _metadata_eval_cases(docs[:count])
    final_data = build_full_eval_set(result, eval_name=eval_name, kb_id=kb_id)
    if not final_data.get('cases'):
        raise DatasetGenerationEmptyError(
            f'dataset generation produced no cases for {eval_name}')
    path = config.storage.base_dir / 'datasets' / eval_name / 'eval_data.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, final_data)
    _log.info('dataset_gen finished %s cases -> %s', len(final_data.get('cases', [])), path)
    return str(path), final_data


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
        hint = ' URL_MAP document_url datasets are not enumerable through /v1/docs; use a local ds_* kb_id or add a remote enumeration adapter.'
    raise KBDocsEmptyError(f'no docs found for kb_id={kb_id} algo_id={algo_id}.{hint}')


def _generate_single_hop_from_kb(
    dataset_source: KBClient,
    docs: list[dict],
    kb_id: str,
    algo_id: str,
    *,
    count: int,
    llm_factory=None,
) -> list[dict]:
    results: list[dict] = []
    for item in docs:
        doc = item.get('doc', {})
        doc_id = doc.get('doc_id', '')
        filename = doc.get('filename', doc_id or 'unknown')
        for chunk in dataset_source.get_chunks(kb_id, doc_id, algo_id):
            if len(chunk.get('content', '')) <= 50:
                continue
            try:
                qa = chat(
                    prompt_generate_single_hop(chunk['content'], filename, doc_id, chunk.get('chunk_id', '')),
                    llm_factory=llm_factory,
                )
            except Exception as exc:
                _log.warning('single-hop generation failed for %s: %s', doc_id, exc)
                continue
            if is_qa_json_valid(qa):
                qa['reference_doc_ids'] = [doc_id]
                qa['reference_chunk_ids'] = [chunk.get('chunk_id', '')]
                results.append({'qa': qa})
                if len(results) >= count:
                    return results
    return results


def _metadata_eval_cases(docs: list[dict]) -> list[dict]:
    cases: list[dict] = []
    for item in docs:
        doc = item.get('doc', {})
        filename = doc.get('filename') or doc.get('name') or doc.get('doc_id', '')
        doc_id = doc.get('doc_id', '')
        if not filename:
            continue
        cases.append({'qa': {
            'reference_doc': [filename],
            'reference_context': [f'知识库中包含文档：{filename}'],
            'question': f'知识库中是否包含名为《{filename}》的文档？',
            'question_type': 1,
            'key_points': [filename],
            'ground_truth': f'是，知识库中包含名为《{filename}》的文档。',
            'reference_chunk_ids': [],
            'reference_doc_ids': [doc_id] if doc_id else [],
        }})
    return cases


def run_eval(
    dataset_id: str,
    target_chat_url: str,
    *,
    cfg: EvoConfig,
    llm_factory=None,
    max_workers: int = 10,
    dataset_name: str = '',
) -> dict[str, Any]:
    _log.info('start eval dataset_id=%s target=%s', dataset_id, target_chat_url)
    eval_data = get_eval_queue(
        dataset_id, dataset_name=dataset_name,
        base_dir=cfg.storage.base_dir, target_chat_url=target_chat_url,
    )
    eval_queue = eval_data['eval_queue']
    if not eval_queue:
        raise EvalDatasetEmptyError(f'eval dataset {dataset_id} has no cases')
    result = create_evaluate_task(eval_queue, llm_factory=llm_factory, max_workers=max_workers)
    report = build_eval_report(result, eval_data)
    path = save_eval_report(dataset_id, report, cfg.storage.base_dir)
    _log.info('eval %s done -> %s', dataset_id, path)
    return report
