"""Qwen `<think>...</think>` stream splitter.

Mirrors the think-handling state machine in
`algorithm/chat/utils/stream_scanner.py::IncrementalScanner` but lives in
evo to avoid pulling chat-runtime deps (rapidfuzz, plugins). Keep the two
in sync if upstream tag conventions ever change.
"""
from __future__ import annotations

_OPEN = '<think>'
_CLOSE = '</think>'


def _partial_tag_at_tail(buf: str, tag: str) -> int | None:
    n = len(tag)
    for k in range(n - 1, 0, -1):
        if buf.endswith(tag[:k]):
            return len(buf) - k
    return None


class ThinkSplitter:
    def __init__(self) -> None:
        self.buf = ''
        self.in_think = False

    def feed(self, chunk: str) -> list[tuple[str, str]]:
        self.buf += chunk
        out: list[tuple[str, str]] = []
        i = seg = 0
        while i < len(self.buf):
            tag = _CLOSE if self.in_think else _OPEN
            if self.buf.startswith(tag, i):
                if i > seg:
                    out.append(('think' if self.in_think else 'text',
                                 self.buf[seg:i]))
                i += len(tag)
                seg = i
                self.in_think = not self.in_think
                continue
            i += 1
        cut = len(self.buf)
        for tag in (_OPEN, _CLOSE):
            pos = _partial_tag_at_tail(self.buf, tag)
            if pos is not None and pos >= seg and pos < cut:
                cut = pos
        if cut > seg:
            out.append(('think' if self.in_think else 'text',
                         self.buf[seg:cut]))
        self.buf = self.buf[cut:]
        return [p for p in out if p[1]]

    def flush(self) -> list[tuple[str, str]]:
        out = self.feed('')
        if self.buf:
            out.append(('think' if self.in_think else 'text', self.buf))
            self.buf = ''
        return out
