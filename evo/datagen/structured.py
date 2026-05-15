from __future__ import annotations
import logging
import random
import re
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from typing import Callable
from evo.datagen.llm import chat
from evo.datagen.prompts import prompt_generate_list, prompt_generate_table
from evo.datagen.validate import normalize_qa_json
from evo.harness.plan import StopRequested

_log = logging.getLogger('evo.datagen.structured')
_TABLE_RE = re.compile(
    '(\\|.+\\|)|(<table[\\s>])|(\\t[^\\n]+\\t)|(^\\s*[^\\n|]+\\s{2,}[^\\n]+\\s{2,}[^\\n]+$)',
    re.IGNORECASE | re.MULTILINE,
)
_LIST_RE = re.compile(
    '(^\\s*[-*•]\\s+\\S)|(^\\s*\\d+[.)、]\\s+\\S)|(^\\s*[一二三四五六七八九十]+[、.]\\s+\\S)', re.MULTILINE
)
PromptBuilder = Callable[[list[str]], str]


def generate_table_questions(
    chunks: list[dict], *, count: int, max_workers: int, llm_factory=None, cancel=None
) -> list[dict]:
    return _generate_structured(
        _candidate_chunks(chunks, _looks_like_table),
        count=count,
        question_type=4,
        prompt_builder=prompt_generate_table,
        max_workers=max_workers,
        llm_factory=llm_factory,
        cancel=cancel,
        label='table',
    )


def generate_list_questions(
    chunks: list[dict], *, count: int, max_workers: int, llm_factory=None, cancel=None
) -> list[dict]:
    return _generate_structured(
        _candidate_chunks(chunks, _looks_like_list),
        count=count,
        question_type=5,
        prompt_builder=prompt_generate_list,
        max_workers=max_workers,
        llm_factory=llm_factory,
        cancel=cancel,
        label='list',
    )


def _candidate_chunks(chunks: list[dict], pred) -> list[dict]:
    rows = [c for c in chunks if pred(c.get('content', ''))]
    random.shuffle(rows)
    return rows


def _looks_like_table(content: str) -> bool:
    return bool(_TABLE_RE.search(content))


def _looks_like_list(content: str) -> bool:
    return bool(_LIST_RE.search(content))


def _generate_structured(
    chunks: list[dict],
    *,
    count: int,
    question_type: int,
    prompt_builder: PromptBuilder,
    max_workers: int,
    llm_factory=None,
    label: str,
    cancel=None,
) -> list[dict]:
    if count <= 0:
        return []
    if not chunks:
        _log.info('%s generation skipped: no candidate chunks', label)
        return []

    def one(chunk: dict) -> dict | None:
        if cancel and cancel():
            return None
        try:
            qa = chat(prompt_builder([chunk['content']]), llm_factory=llm_factory)
        except Exception as exc:
            _log.info('%s generation failed: %s', label, exc)
            return None
        if not isinstance(qa, dict) or qa.get('skip'):
            return None
        qa = normalize_qa_json(qa)
        if not qa:
            return None
        qa['question_type'] = question_type
        qa['reference_doc'] = [chunk.get('filename', '')]
        qa['reference_context'] = [chunk['content']]
        qa['reference_doc_ids'] = [chunk.get('doc_id', '')]
        qa['reference_chunk_ids'] = [chunk.get('chunk_id', '')]
        if not qa.get('generate_reason'):
            qa['generate_reason'] = f'基于{label}结构化片段生成'
        return {'qa': qa}

    results: list[dict] = []
    executor = ThreadPoolExecutor(max_workers=max(1, max_workers))
    pending = {}
    iterator = iter(chunks[: max(count * 3, count)])

    def submit_next() -> bool:
        if cancel and cancel():
            return False
        try:
            chunk = next(iterator)
        except StopIteration:
            return False
        pending[executor.submit(one, chunk)] = chunk
        return True

    try:
        while len(pending) < max(1, max_workers) and submit_next():
            pass
        while pending:
            if cancel and cancel():
                raise StopRequested(at_step='case')
            if len(results) >= count:
                break
            done, _ = wait(pending, timeout=0.2, return_when=FIRST_COMPLETED)
            if not done:
                continue
            f = done.pop()
            pending.pop(f, None)
            item = f.result()
            if item:
                results.append(item)
            if len(results) >= count:
                break
            submit_next()
    finally:
        for future in pending:
            future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)
    _log.info('%s generation done: %s/%s', label, len(results), count)
    return results
