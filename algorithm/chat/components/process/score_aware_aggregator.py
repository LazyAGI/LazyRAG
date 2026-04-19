from collections import defaultdict
from typing import List, Optional

from lazyllm import LOG
from lazyllm.tools.rag.doc_node import DocNode


class ScoreAwareParentAggregator:
    '''Aggregate child DocNodes to their parent group while preserving hit-density signal.

    After a fine-grained retriever (e.g. group='line') returns nodes, the default
    lazyllm find_parent path deduplicates parents via a set, discarding how many
    children hit the same parent and what their similarity scores were. This component
    re-implements the parent mapping so that:

      aggregated_score = max(child_similarity_scores) + hit_weight * hit_count

    A block that has 10 matching lines will therefore rank higher than a block with
    only 1 matching line, even when both blocks contain the same best-scoring line.
    '''

    def __init__(self, document, target_group: str, hit_weight: float = 0.05):
        '''
        Args:
            document: lazyllm Document (or UrlDocument) handle used to resolve
                      parent nodes across the full group tree.
            target_group: the group name to map nodes into, e.g. 'block'.
            hit_weight: bonus added per child node hit. Default 0.05, meaning
                        20 child hits contribute +1.0 on top of the max score.
        '''
        self._document = document
        self._target_group = target_group
        self._hit_weight = hit_weight

    def __call__(self, nodes: List[DocNode]) -> List[DocNode]:
        if not nodes:
            return nodes

        # If nodes are already in the target group, nothing to do.
        if nodes[0]._group == self._target_group:
            return nodes

        # --- Step 1: collect per-parent-uid stats from child nodes ---
        # parent uid -> {'hits': int, 'max_score': float}
        # node.parent is either a DocNode object (in-process) or a uid string (remote store).
        parent_stats: dict = defaultdict(lambda: {'hits': 0, 'max_score': 0.0})

        direct_parent_group: Optional[str] = None

        for node in nodes:
            parent = node._parent
            if parent is None:
                continue

            if isinstance(parent, str):
                # parent is a uid string (remote / db-backed node)
                uid = parent
            elif hasattr(parent, '_uid'):
                # DocNode or any object carrying _uid (tests may use SimpleNamespace)
                uid = parent._uid
                if direct_parent_group is None:
                    direct_parent_group = getattr(parent, '_group', None)
            else:
                continue

            score = node.similarity_score or 0.0
            stats = parent_stats[uid]
            stats['hits'] += 1
            if score > stats['max_score']:
                stats['max_score'] = score

        if not parent_stats:
            LOG.warning(
                '[ScoreAwareParentAggregator] No parent uids found on nodes; '
                'falling back to original document.find() behaviour.'
            )
            return self._document.find(self._target_group)(nodes)

        # Warn when parent group != target group (multi-level jump).
        # Aggregation stats are still based on the direct children, which is a
        # reasonable approximation, but semantics are less precise.
        if direct_parent_group and direct_parent_group != self._target_group:
            LOG.warning(
                f'[ScoreAwareParentAggregator] Direct parent group '
                f'"{direct_parent_group}" != target "{self._target_group}". '
                f'Score aggregation is based on direct child nodes only.'
            )

        # --- Step 2: use lazyllm's find() to get deduplicated target nodes ---
        target_nodes: List[DocNode] = self._document.find(self._target_group)(nodes)

        if not target_nodes:
            return target_nodes

        # --- Step 3: attach aggregated score to each target node ---
        # For direct-parent case, the target node uid IS the parent uid we tracked.
        # For multi-level case we fall back to 0 bonus (no match in parent_stats).
        for target_node in target_nodes:
            stats = parent_stats.get(target_node._uid)
            if stats:
                target_node.similarity_score = (
                    stats['max_score'] + self._hit_weight * stats['hits']
                )
            # If no direct mapping (multi-level), leave similarity_score unchanged.

        return sorted(target_nodes, key=lambda n: n.similarity_score or 0.0, reverse=True)
