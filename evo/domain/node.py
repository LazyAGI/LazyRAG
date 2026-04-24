from __future__ import annotations

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


MOCK_NODE: NodeInfo = {
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
