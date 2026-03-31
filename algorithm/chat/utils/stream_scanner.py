# lazyrag/utils/stream_scanner.py
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections import OrderedDict
from html import escape
from typing import Dict, List, Tuple
from rapidfuzz import fuzz

from chat.utils.url import get_url_basename

__all__ = ['BasePlugin', 'CitationPlugin', 'ImagePlugin', 'IncrementalScanner']


IMAGE_PATTERN = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')

# Qwen-style think delimiters (lengths 7 and 8; must stay in sync with parsers elsewhere)
_THINK_OPEN = '<think>'
_THINK_CLOSE = '</think>'


# ============================================================
# BasePlugin
# ============================================================
class BasePlugin(ABC):
    prefix_set: set[str]

    @abstractmethod
    def match(self, src: str, pos: int) -> Tuple[int, str] | None:
        ...

    def last_incomplete_pos(self, buf: str) -> int | None:
        return None

    def collect(self) -> List[Dict[str, str]]:
        return []


# ============================================================
# CitationPlugin  [[id]]
# ============================================================
class CitationPlugin(BasePlugin):
    prefix_set = {'['}
    _pat = re.compile(r'\[\[(\d+)\]\]')

    def __init__(self, refs: Dict[int, object]):
        self.refs = refs
        self._collected: 'OrderedDict[int, Dict[str, str]]' = OrderedDict()

    def match(self, src: str, pos: int):
        m = self._pat.match(src, pos)
        if not m:
            return None
        idx = int(m.group(1))
        node = self.refs.get(idx)
        if not node or not node.text:
            return (m.end(), '')  # 删除未知编号
        self._collected.setdefault(idx, self._source_node(idx, node))
        return (m.end(), self._citation(idx, node))

    @staticmethod
    def _citation(idx: int, node):
        title = escape(node.global_metadata.get('file_name', 'title'))
        return f'[{idx}](#source "{title}")'

    @staticmethod
    def _source_node(idx: int, node):
        gm = node.global_metadata
        metadata = node.metadata
        images = {get_url_basename(url): url for url in metadata.get('images', [])}

        def _recover_image_path(match: re.Match) -> str:
            """re.sub 回调：若本地存在图片，则收集并替换为占位符。"""
            title, image_path = match.groups()
            return f'![{title}]({images.get(image_path, image_path)})'

        return {
            'index': idx,
            'number': metadata.get('store_num') or metadata.get('lazyllm_store_num') or -1,
            'page': metadata.get('page', -1),
            'bbox': metadata.get('bbox', []),
            'docid': gm.get('docid', 'file_id_example'),
            'kb_id': gm.get('kb_id', 'kb_id_example'),
            'file_name': gm.get('file_name', 'title_example'),
            'id': node._uid,
            'text': IMAGE_PATTERN.sub(_recover_image_path, node.text) if images else node.text,
            'group': node._group
        }

    def collect(self):
        return list(self._collected.values())

    def last_incomplete_pos(self, buf: str) -> int | None:
        # 1) 未闭合的 '[[...'
        last_double = buf.rfind('[[')
        if last_double != -1 and ']]' not in buf[last_double + 2:]:
            return last_double
        # 2) 缓冲以单 '[' 结尾，可能下一片段是 '['
        if buf.endswith('['):
            return len(buf) - 1
        return None


# ============================================================
# ImagePlugin  ![alt](url)
# ============================================================
class ImagePlugin(BasePlugin):
    prefix_set = {'!'}
    # 使用非贪婪匹配 alt 与 url，使 alt 中可以包含括号等字符
    _pat = re.compile(r'!\[(.*?)\]\((.*?)\)')

    def __init__(self, url_map: Dict[str, str]):
        self.url_map = url_map

    def match(self, src: str, pos: int):
        m = self._pat.match(src, pos)
        if not m:
            return None
        alt, url = m.group(1), m.group(2)
        if url in self.url_map:
            return (m.end(), f'![{alt}]({self.url_map[url]})')
        # 模糊匹配相似度大于80%的最相似的图片
        best_key = None
        best_score = 0

        for k in self.url_map.keys():
            score = fuzz.ratio(url, k)  # 0 ~ 100
            if score >= 80 and score > best_score:
                best_score = score
                best_key = k

        if best_key:
            mapped = self.url_map[best_key]
            return (m.end(), f'![{alt}]({mapped})')

        return (m.end(), '')

    def last_incomplete_pos(self, buf: str) -> int | None:
        """
        更精确地检测图像 token 是否为未闭合：
        - 搜索最后一个 '![', 然后按顺序检查是否存在 ']'、'('、')'。
        - 只在这些结构均完整时才认为 token 可能完整，其他情况返回 last_img 表示需要保留到下一 chunk。
        """
        last_img = buf.rfind('![')
        if last_img == -1:
            if buf.endswith('!'):
                return len(buf) - 1
            return None

        # 从 last_img + 2 开始查找 ']'（结束 alt）
        alt_end = buf.find(']', last_img + 2)
        if alt_end == -1:
            # alt 未闭合
            return last_img

        # 在 alt_end 之后寻找 '(' 开始 url
        paren_start = buf.find('(', alt_end + 1)
        if paren_start == -1:
            # '(' 未出现（还没到 url 部分）
            return last_img

        # 在 paren_start 之后寻找 ')' 结束 url
        paren_end = buf.find(')', paren_start + 1)
        if paren_end == -1:
            # url 未闭合
            return last_img

        # 如果都找到了，说明有完整的 '![...](...)'，返回 None（没有未闭合）
        return None


# ============================================================
# IncrementalScanner
# ============================================================
class IncrementalScanner:
    """BODY / THINK 状态流式解析器。"""

    def __init__(self, plugins: List[BasePlugin], initial_state: str = 'BODY'):
        self.plugins = plugins
        self.state = initial_state
        self.buf = ''

    # ---------------- helpers ----------------
    @staticmethod
    def _partial_tag_start(buf: str, tag: str) -> int | None:
        """若缓冲以 `tag` 的**不完整前缀**结尾，返回该前缀在缓冲中的起始索引。
        例如 buf="<thi" & tag="`think`" → 返回 len(buf)-4。
        完整匹配或无前缀返回 None。
        """
        n = len(tag)
        # 只考虑严格的“尾部是 tag 的真前缀”，完整不算
        for k in range(n - 1, 0, -1):
            if buf.endswith(tag[:k]):
                return len(buf) - k
        return None

    # ---------------- public ----------------
    def feed(self, chunk: str) -> List[Tuple[str, str]]:
        self.buf += chunk
        out: List[Tuple[str, str]] = []
        i = seg_start = 0

        while i < len(self.buf):
            # ---- think 开关 ----
            if self.state == 'BODY' and self.buf.startswith(_THINK_OPEN, i):
                if i > seg_start:
                    out.append(('text', self.buf[seg_start:i]))
                i += len(_THINK_OPEN)
                seg_start = i
                self.state = 'THINK'
                continue
            if self.state == 'THINK' and self.buf.startswith(_THINK_CLOSE, i):
                if i > seg_start:
                    out.append(('think', self.buf[seg_start:i]))
                i += len(_THINK_CLOSE)
                seg_start = i
                self.state = 'BODY'
                continue

            # ---- 插件尝试匹配 ----
            handled = False
            for pl in self.plugins:
                if self.buf[i] not in pl.prefix_set:
                    continue
                res = pl.match(self.buf, i)
                if res:
                    end, replacement = res
                    if i > seg_start:
                        out.append((self._field(), self.buf[seg_start:i]))
                    out.append((self._field(), replacement))
                    i, seg_start, handled = end, end, True
                    break
            if not handled:
                i += 1

        # ---- 截取安全区 ----
        cut = len(self.buf)
        # 1) 插件报告的未闭合 token
        for pl in self.plugins:
            pos = pl.last_incomplete_pos(self.buf)
            if pos is not None and pos >= seg_start and pos < cut:
                cut = pos
        # 2) THINK 标签的未完整前缀（`think` / `/think`）
        for tag in (_THINK_OPEN, _THINK_CLOSE):
            pos = self._partial_tag_start(self.buf, tag)
            if pos is not None and pos >= seg_start and pos < cut:
                cut = pos

        if cut > seg_start:
            out.append((self._field(), self.buf[seg_start:cut]))
        self.buf = self.buf[cut:]
        return [p for p in out if p[1]]

    def flush(self) -> List[Tuple[str, str]]:
        tail = self.feed('')
        if self.buf:
            tail.append((self._field(), self.buf))
            self.buf = ''
        return tail

    # ---------------- helpers ----------------
    def _field(self) -> str:
        return 'think' if self.state == 'THINK' else 'text'
