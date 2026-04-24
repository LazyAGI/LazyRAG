from __future__ import annotations

import os

from evo.domain.node import MOCK_NODE, NodeInfo


def http_get_node(node_id: str) -> NodeInfo | None:
    from chat.pipelines.builders.get_retriever import get_remote_docment
    server_url = os.getenv("LAZYRAG_DOCUMENT_SERVER_URL")
    if server_url is None:
        return MOCK_NODE
    document = get_remote_docment(server_url)
    if document is None:
        return MOCK_NODE
    node = document.get_nodes(node_id)
    if node is None:
        return MOCK_NODE

    return NodeInfo(
        id=node.id,
        docid=node.docid,
        kb_id=node.kb_id,
        file_name=node.file_name,
        text=node.text,
        group=node.group,
        page=node.page,
        index=node.index,
        number=node.number,
        bbox=node.bbox,
    )
