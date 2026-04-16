"""Walk an execution_tree: thin wrapper over domain parsing + node resolution."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from evo.domain.models import _walk_execution_tree, _extract_query, ModuleOutput


def get_node(node_id: str) -> dict[str, Any] | None:
    return {"file_name": node_id, "id": node_id, "text": f"[mock] {node_id}", "group": "block"}


@dataclass
class NodeInfo:
    id: str
    doc_id: str
    file_name: str
    text: str
    raw: dict[str, Any]


class NodeStore:
    """Deduplicating store for resolved nodes."""

    def __init__(self) -> None:
        self._nodes: dict[str, NodeInfo] = {}

    def add(self, node_id: str) -> NodeInfo | None:
        if node_id in self._nodes:
            return self._nodes[node_id]
        raw = get_node(node_id)
        if raw is None:
            return None
        info = NodeInfo(id=node_id, doc_id=raw.get("doc_id", ""), file_name=raw.get("file_name", ""), text=raw.get("text", ""), raw=raw)
        self._nodes[node_id] = info
        return info

    def get(self, node_id: str) -> NodeInfo | None:
        return self._nodes.get(node_id)

    def all(self) -> dict[str, NodeInfo]:
        return dict(self._nodes)

    def __len__(self) -> int:
        return len(self._nodes)

    def __contains__(self, node_id: str) -> bool:
        return node_id in self._nodes


@dataclass
class StepResult:
    key: str
    name: str
    mod: ModuleOutput
    input_summary: Any = None
    output_summary: Any = None


@dataclass
class TraceWalkResult:
    trace_id: str
    query: str
    steps: list[StepResult]
    flow_skeleton: list[dict[str, Any]]
    pipeline: list[str]
    node_store: NodeStore = field(default_factory=NodeStore)


def _summarize_io(data: Any) -> Any:
    if isinstance(data, list):
        ids = [item["id"] for item in data if isinstance(item, dict) and "id" in item]
        if ids:
            return ids
        if data and isinstance(data[0], str):
            return data[0]
        return data
    if isinstance(data, dict):
        args = data.get("args")
        if isinstance(args, list) and args:
            inner = _summarize_io(args)
            kwargs = data.get("kwargs", {})
            if kwargs:
                return {"query": inner, **kwargs} if isinstance(inner, str) else {"args": inner, **kwargs}
            return inner
        if "id" in data:
            return data["id"]
        return data
    return data


def _collect_ids(summary: Any) -> list[str]:
    if isinstance(summary, list) and summary and isinstance(summary[0], str):
        return summary
    if isinstance(summary, dict):
        ids: list[str] = []
        for v in summary.values():
            ids.extend(_collect_ids(v))
        return ids
    return []


def walk_trace(trace_data: dict[str, Any]) -> TraceWalkResult:
    tree = trace_data.get("execution_tree", {})
    pipeline, modules, skeleton = _walk_execution_tree(tree)

    steps: list[StepResult] = []
    store = NodeStore()
    for key in pipeline:
        mod = modules[key]
        in_sum = _summarize_io(mod.input)
        out_sum = _summarize_io(mod.output)
        steps.append(StepResult(key=key, name=key.split("_")[0] if "_" in key else key, mod=mod, input_summary=in_sum, output_summary=out_sum))
        for nid in _collect_ids(in_sum) + _collect_ids(out_sum):
            store.add(nid)

    return TraceWalkResult(
        trace_id=trace_data.get("trace_id", ""),
        query=_extract_query(tree),
        steps=steps, flow_skeleton=skeleton, pipeline=pipeline, node_store=store,
    )


def walk_trace_file(path: str | Path) -> dict[str, TraceWalkResult]:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return {
        key: walk_trace(val)
        for key, val in raw.items()
        if key != "count" and isinstance(val, dict) and "execution_tree" in val
    }
