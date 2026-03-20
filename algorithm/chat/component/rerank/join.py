from typing import List, Tuple, Any

from lazyllm import LOG
from lazyllm.tools.rag import DocNode


class RRFJoinComponent:
    def __init__(self, top_k: int = 0, **kwargs):
        self.top_k = top_k

    def reciprocal_rerank_fusion(self, results: Tuple[str, List[DocNode]], top_k: int = 0) -> List[DocNode]:
        k = 60.0  # `k` is a parameter used to control the impact of outlier rankings.
        fused_scores = {}
        uid_to_node = {}

        # compute reciprocal rank scores
        for _, nodes in results:
            for rank, node in enumerate(nodes):
                # print(f"NODE_TEXT: {node.text}")
                # print('--------------------------------')
                uid = node._uid
                uid_to_node[uid] = node
                if uid not in fused_scores:
                    fused_scores[uid] = 0.0
                fused_scores[uid] += 1.0 / (rank + k)

        # sort results
        reranked_results = dict(sorted(fused_scores.items(), key=lambda x: x[1], reverse=True))

        # adjust node scores
        reranked_nodes: List[DocNode] = []
        for uid, score in reranked_results.items():
            reranked_nodes.append(uid_to_node[uid])

        return reranked_nodes[:top_k] if top_k > 0 else reranked_nodes


    def __call__(self, *args, **kwargs: Any) -> List[Any]:
        input = []
        for arg in args:
            input.append(arg)
        if not input:
            return []

        if len(input) <= 1:
            return input[0][:self.top_k] if self.top_k > 0 else input[0]

        return self.reciprocal_rerank_fusion([(index, result) for index, result in enumerate(input)], top_k=self.top_k)
