from __future__ import annotations

METRIC_DIRECTION: dict[str, str] = {
    'chunk_recall_at_k': '+', 'doc_recall_at_k': '+',
    'chunk_hit_at_1': '+', 'chunk_hit_at_3': '+', 'chunk_hit_at_5': '+',
    'doc_hit_at_1': '+', 'doc_hit_at_3': '+', 'doc_hit_at_5': '+',
    'chunk_mrr': '+', 'doc_mrr': '+',
    'chunk_input_recall': '+', 'chunk_output_recall': '+', 'chunk_recall_delta': '+',
    'doc_input_recall': '+', 'doc_output_recall': '+', 'doc_recall_delta': '+',
    'chunk_gt_survival_rate': '+', 'doc_gt_survival_rate': '+',
    'chunk_precision_at_k': '+', 'doc_precision_at_k': '+',
    'chunk_unique_precision': '+', 'doc_unique_precision': '+',
    'answer_gt_overlap': '+', 'context_utilization': '+',
    'answer_query_coverage': '+', 'answer_gt_semantic': '+',
    'context_semantic_utilization': '+', 'query_answer_semantic': '+',
    'score_at_first_gt': '+', 'score_gt_vs_non_gt': '+', 'score_active_ratio': '+',
    'chunk_page_diversity': '+',
    'chunk_gt_dropped': '-', 'doc_gt_dropped': '-',
    'repetition_rate': '-',
    'tag_retrieval_miss': '-', 'tag_ranking_fail': '-',
    'tag_reranker_drop': '-', 'tag_generation_drift': '-',
}

__all__ = ['METRIC_DIRECTION']
