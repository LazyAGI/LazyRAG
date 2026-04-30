from __future__ import annotations
import logging
import random
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from evo.datagen.corpus import build_corpus_index
from evo.datagen.kb_client import KBClient
from evo.datagen.llm import chat
from evo.datagen.prompts import prompt_generate_multihop
from evo.datagen.validate import normalize_qa_json

_log = logging.getLogger('evo.datagen.multi_hop')


def generate_multi_hop(
    ds: KBClient, kb_id: str, algo_id: str, *, max_questions: int = 20, llm_factory=None, max_workers: int = 8
) -> list[dict]:
    idx = build_corpus_index(ds, kb_id, algo_id, max_workers=max_workers)
    return generate_multi_hop_from_chunks(
        idx.chunks, count=max_questions, max_workers=max_workers, llm_factory=llm_factory
    )


def generate_multi_hop_from_chunks(chunks: list[dict], *, count: int, max_workers: int, llm_factory=None) -> list[dict]:
    if count <= 0:
        return []
    pairs = _make_pairs(chunks, max(count * 4, count))
    if not pairs:
        _log.info('multi-hop generation skipped: no chunk pairs')
        return []

    def one(pair: tuple[dict, dict]) -> dict | None:
        a, b = pair
        bridge = _bridge_entity(a, b)
        path = f"{a.get('filename', '')} -> {bridge} -> {b.get('filename', '')}"
        try:
            qa = chat(prompt_generate_multihop(bridge, path, a['content'], b['content']), llm_factory=llm_factory)
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
        qa['question_type'] = 2
        qa['reference_doc'] = [a.get('filename', ''), b.get('filename', '')]
        qa['reference_context'] = [a['content'], b['content']]
        qa['reference_doc_ids'] = [a.get('doc_id', ''), b.get('doc_id', '')]
        qa['reference_chunk_ids'] = [a.get('chunk_id', ''), b.get('chunk_id', '')]
        if not qa.get('generate_reason'):
            qa['generate_reason'] = qa.get('reason') or '跨片段双跳推理生成'
        return {'qa': qa}

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, max_workers)) as executor:
        futures = [executor.submit(one, p) for p in pairs]
        for f in as_completed(futures):
            if len(results) >= count:
                break
            item = f.result()
            if item:
                results.append(item)
    _log.info('multi-hop generation done: %s/%s', len(results), count)
    return results


def _make_pairs(chunks: list[dict], limit: int) -> list[tuple[dict, dict]]:
    rows = list(chunks)
    random.shuffle(rows)
    by_doc: dict[str, list[dict]] = {}
    for row in rows:
        by_doc.setdefault(str(row.get('doc_id') or ''), []).append(row)
    docs = [doc for (doc, vals) in by_doc.items() if doc and vals]
    pairs: list[tuple[dict, dict]] = []
    for i, doc_id in enumerate(docs):
        other_id = docs[(i + 1) % len(docs)] if len(docs) > 1 else doc_id
        if doc_id == other_id and len(by_doc[doc_id]) < 2:
            continue
        a = random.choice(by_doc[doc_id])
        b = random.choice(by_doc[other_id])
        if a is not b:
            pairs.append((a, b))
        if len(pairs) >= limit:
            break
    return pairs


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
