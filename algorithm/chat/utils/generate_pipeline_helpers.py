import os

from lazyllm.components.formatter import encode_query_with_filepaths
from lazyllm.tools.rag.doc_node import DocNode, ImageDocNode

from config import config as _cfg


def _candidate_upload_host_dirs() -> list:
    configured_host_dir = _cfg['upload_host_dir']
    algorithm_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../'))
    repo_root = os.path.abspath(os.path.join(algorithm_root, '..'))
    candidates = [
        configured_host_dir,
        './data/core/uploads',
        '../data/core/uploads',
        os.path.join(algorithm_root, 'data/core/uploads'),
        os.path.join(repo_root, 'data/core/uploads'),
    ]
    resolved = []
    for candidate in candidates:
        if not candidate:
            continue
        normalized = os.path.abspath(candidate)
        if normalized not in resolved:
            resolved.append(normalized)
    return resolved


def _resolve_shared_upload_path(path):
    if not isinstance(path, str) or not path:
        return None
    if os.path.exists(path):
        return path
    if not _cfg['local_naive_debug']:
        return None
    shared_upload_dir = _cfg['shared_upload_dir']
    if path.startswith(shared_upload_dir):
        for upload_host_dir in _candidate_upload_host_dirs():
            candidate = path.replace(shared_upload_dir, upload_host_dir, 1)
            if os.path.exists(candidate):
                return candidate
    return None


def _is_image_node(node):
    return isinstance(node, ImageDocNode)


def _is_text_node(node):
    return isinstance(node, DocNode) and not isinstance(node, ImageDocNode)


def _image_path(node):
    if not _is_image_node(node):
        return None
    metadata = getattr(node, 'metadata', None) or {}
    candidates = [
        metadata.get('source_path'),
        metadata.get('normalized_source_path'),
        getattr(node, 'image_path', None),
    ]
    for path in candidates:
        resolved = _resolve_shared_upload_path(path)
        if resolved:
            return resolved
    return None


def _has_image_nodes(nodes, **_):
    return any(_is_image_node(n) for n in (nodes or []))


def _text_nodes(nodes, **_):
    return [n for n in (nodes or []) if _is_text_node(n)]


def _image_nodes(nodes, **_):
    return [n for n in (nodes or []) if _is_image_node(n)]


def _merge_text_and_images(text_nodes, all_nodes, **_):
    return list(text_nodes or []) + _image_nodes(all_nodes)


def build_multimodal_query_with_images(query, nodes, image_files=None):
    paths = []
    for node in (nodes or []):
        path = _image_path(node)
        if path:
            paths.append(path)
    for path in (image_files or []):
        resolved = _resolve_shared_upload_path(path)
        if resolved:
            paths.append(resolved)
    if not paths:
        return query
    return encode_query_with_filepaths(query, list(dict.fromkeys(paths)))
