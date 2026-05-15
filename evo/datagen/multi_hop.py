from __future__ import annotations
import logging
import random
import re
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from evo.datagen.corpus import build_corpus_index
from evo.datagen.kb_client import KBClient
from evo.datagen.llm import chat
from evo.datagen.prompts import prompt_generate_multihop, prompt_generate_single_doc_multihop
from evo.datagen.validate import normalize_qa_json
from evo.harness.plan import StopRequested

_log = logging.getLogger('evo.datagen.multi_hop')


def generate_multi_hop(
    ds: KBClient, kb_id: str, algo_id: str, *, max_questions: int = 20, llm_factory=None, max_workers: int = 8
) -> list[dict]:
    idx = build_corpus_index(ds, kb_id, algo_id, max_workers=max_workers)
    return generate_multi_hop_from_chunks(
        idx.chunks, count=max_questions, max_workers=max_workers, llm_factory=llm_factory
    )


def generate_multi_hop_from_chunks(
    chunks: list[dict], *, count: int, max_workers: int, llm_factory=None, cancel=None
) -> list[dict]:
    if count <= 0:
        return []
    pairs = _make_pairs(chunks, max(count * 4, count))
    if not pairs:
        _log.info('multi-hop generation skipped: no chunk pairs')
        return []

    def one(pair: tuple[dict, dict, int]) -> dict | None:
        if cancel and cancel():
            return None
        a, b, question_type = pair
        path = _path_desc(a, b, question_type)
        try:
            if question_type == 2:
                qa = chat(
                    prompt_generate_single_doc_multihop(path, a['content'], b['content']),
                    llm_factory=llm_factory,
                )
            else:
                qa = chat(
                    prompt_generate_multihop(_bridge_entity(a, b), path, a['content'], b['content']),
                    llm_factory=llm_factory,
                )
        except Exception as exc:
            _log.info('multi-hop generation failed: %s', exc)
            return None
        if not isinstance(qa, dict):
            return None
        if 'multi_hop_question' in qa and 'question' not in qa:
            qa['question'] = qa.pop('multi_hop_question')
        qa = normalize_qa_json(qa)
        if not qa:
            return None
        qa['question_type'] = question_type
        qa['reference_doc'] = _refs(a.get('filename', ''), b.get('filename', ''))
        qa['reference_context'] = [a['content'], b['content']]
        qa['reference_doc_ids'] = _refs(a.get('doc_id', ''), b.get('doc_id', ''))
        qa['reference_chunk_ids'] = [a.get('chunk_id', ''), b.get('chunk_id', '')]
        if not qa.get('generate_reason'):
            qa['generate_reason'] = qa.get('reason') or ('单文档双跳推理生成' if question_type == 2 else '跨文档双跳推理生成')
        return {'qa': qa}

    results: list[dict] = []
    executor = ThreadPoolExecutor(max_workers=max(1, max_workers))
    pending = {}
    iterator = iter(pairs)

    def submit_next() -> bool:
        if cancel and cancel():
            return False
        try:
            pair = next(iterator)
        except StopIteration:
            return False
        pending[executor.submit(one, pair)] = pair
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
    _log.info('multi-hop generation done: %s/%s', len(results), count)
    return results


def _make_pairs(chunks: list[dict], limit: int) -> list[tuple[dict, dict, int]]:
    rows = list(chunks)
    random.shuffle(rows)
    by_doc: dict[str, list[dict]] = {}
    for row in rows:
        by_doc.setdefault(str(row.get('doc_id') or ''), []).append(row)
    same = _same_doc_pairs(by_doc, (limit + 1) // 2)
    cross = _cross_doc_pairs(by_doc, limit // 2)
    pairs = []
    for i in range(max(len(same), len(cross))):
        pairs.extend(xs[i] for xs in (same, cross) if i < len(xs))
    return pairs[:limit]


def _same_doc_pairs(by_doc: dict[str, list[dict]], limit: int) -> list[tuple[dict, dict, int]]:
    pairs = []
    for vals in by_doc.values():
        if len(vals) < 2:
            continue
        random.shuffle(vals)
        for i in range(min(len(vals) - 1, limit - len(pairs))):
            pairs.append((vals[i], vals[i + 1], 2))
        if len(pairs) >= limit:
            break
    return pairs


def _cross_doc_pairs(by_doc: dict[str, list[dict]], limit: int) -> list[tuple[dict, dict, int]]:
    docs = [doc for doc, vals in by_doc.items() if doc and vals]
    return [
        (random.choice(by_doc[doc]), random.choice(by_doc[docs[(i + 1) % len(docs)]]), 3)
        for i, doc in enumerate(docs[:limit])
        if len(docs) > 1
    ]


def _path_desc(a: dict, b: dict, question_type: int) -> str:
    if question_type == 2:
        return f"{a.get('filename', '')} 内片段1 -> 同文档片段2"
    bridge = _bridge_entity(a, b)
    return f"{a.get('filename', '')} -> {bridge} -> {b.get('filename', '')}"


def _refs(a: str, b: str) -> list[str]:
    return [a] if a == b else [a, b]


def _bridge_entity(a: dict, b: dict) -> str:
    common = _terms(a['content']) & _terms(b['content'])
    if common:
        return max(common, key=len)
    for row in (a, b):
        filename = str(row.get('filename') or '').strip()
        if filename:
            return filename[:60]
    return '核心实体'


def _terms(text: str) -> set[str]:
    chinese = set(re.findall('[\\u4e00-\\u9fff]{2,12}', text))
    latin = {m for m in re.findall('[A-Z][A-Za-z0-9_-]{2,}', text)}
    return chinese | latin
