from __future__ import annotations

import os
from typing import Callable, TypedDict


class NodeInfo(TypedDict, total=False):
    id: str
    docid: str
    kb_id: str
    file_name: str
    text: str
    group: str
    page: int
    index: int
    number: int
    bbox: list[int]


NodeResolver = Callable[[str], "NodeInfo | None"]


_MOCK_NODE: NodeInfo = {
    "id": "mock-node",
    "docid": "mock-docid",
    "kb_id": "default",
    "file_name": "mock.pdf",
    "text": "mock content",
    "group": "block",
    "page": 0,
    "index": 0,
    "number": 0,
    "bbox": [0, 0, 0, 0],
}


def get_node(node_id: str) -> NodeInfo | None:
    from chat.pipelines.builders.get_retriever import get_remote_docment
    server_url = os.getenv("LAZYRAG_DOCUMENT_SERVER_URL")
    if server_url is None:
        return _MOCK_NODE
    document = get_remote_docment(server_url)
    if document is None:
        return _MOCK_NODE
    node = document.get_nodes(node_id)
    if node is None:
        return _MOCK_NODE

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
