from __future__ import annotations

import logging
from typing import Any

from evo.datagen.graph import ParallelKGBuilder
from evo.datagen.kb_client import KBClient

_log = logging.getLogger('evo.datagen.multi_hop')


def generate_multi_hop(
    ds: KBClient, kb_id: str, algo_id: str,
    *, max_questions: int = 20, llm_factory=None, max_workers: int = 10,
) -> list[dict]:
    def _get_all_chunks() -> list[dict]:
        chunks: list[dict] = []
        try:
            doc_list = ds.get_doc_list(kb_id, algo_id)
        except Exception as exc:
            _log.warning('get_doc_list failed: %s', exc)
            return chunks
        for doc_item in doc_list:
            doc = doc_item.get('doc', {})
            doc_id = doc.get('doc_id', '')
            doc_name = doc.get('name', doc.get('filename', doc_id))
            try:
                doc_chunks = ds.get_all_chunks(kb_id, doc_id, algo_id)
            except Exception as exc:
                _log.warning('get_all_chunks failed for %s: %s', doc_name, exc)
                continue
            for c in doc_chunks:
                if not c.get('doc_id'):
                    c['doc_id'] = doc_id
            chunks.extend(doc_chunks)
            _log.info('doc %s chunks: %s', doc_name, len(doc_chunks))
        return chunks

    builder = ParallelKGBuilder(llm_factory=llm_factory, max_workers=max_workers)
    builder.build_global_graph_from_all_docs(_get_all_chunks)
    cross_list = builder.generate_multi_hop_questions(max_questions=max_questions, cross_doc=True)
    single_list = builder.generate_multi_hop_questions(max_questions=max_questions, cross_doc=False)
    questions = cross_list + single_list
    return [{'qa': item} for item in questions]
