from __future__ import annotations


def calculate_metrics(reference_chunk_ids, reference_doc_ids, retrieve_chunk_ids, retrieve_doc_ids):
    ref_chunks = set(reference_chunk_ids)
    ref_docs = set(reference_doc_ids)
    ret_chunks = set(retrieve_chunk_ids)
    ret_docs = set(retrieve_doc_ids)
    hit_chunks = len(ref_chunks & ret_chunks)
    hit_docs = len(ref_docs & ret_docs)
    context_recall = hit_chunks / len(ref_chunks) if ref_chunks else 0.0
    doc_recall = hit_docs / len(ref_docs) if ref_docs else 0.0
    return {'context_recall': round(context_recall, 4), 'doc_recall': round(doc_recall, 4)}
