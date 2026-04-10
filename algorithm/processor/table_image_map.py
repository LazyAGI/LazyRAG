import json
from typing import Any, Dict, List, Optional


def normalize_table_image_map(value: Any) -> List[Dict[str, str]]:
    """将 table_image_map 统一为 list[dict] 格式，兼容旧版 dict 和新版 JSON 字符串。"""
    if not value:
        return []
    if isinstance(value, (bytes, bytearray)):
        value = value.decode('utf-8')
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return []
    if isinstance(value, dict):
        return [{'content': k, 'image': v} for k, v in value.items()]
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if isinstance(item, dict) and item.get('content') and item.get('image'):
            result.append({'content': str(item['content']), 'image': str(item['image'])})
    return result


def merge_table_image_maps(*values: Any) -> List[Dict[str, str]]:
    """合并多个 table_image_map，相同 content 保留最后出现的。"""
    merged = {}
    for value in values:
        for item in normalize_table_image_map(value):
            merged[item['content']] = item['image']
    return [{'content': k, 'image': v} for k, v in merged.items()]


def serialize_table_image_map(value: Any) -> Optional[str]:
    """序列化为 JSON 字符串，避免 OpenSearch 将 dict key 展开为动态 mapping。"""
    normalized = normalize_table_image_map(value)
    return json.dumps(normalized, ensure_ascii=False) if normalized else None
