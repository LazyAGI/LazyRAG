from __future__ import annotations

import re


def clean_and_filter_chunk(content: str | None) -> str | None:
    if not content:
        return None
    pattern1 = r'!\[]\(/mnt/lustre/share_data.*?\.(jpg|png|jpeg|gif|bmp)'
    content = re.sub(pattern1, '', content, flags=re.IGNORECASE)
    pattern2 = r'/mnt/lustre/share_data.*?\.(jpg|png|jpeg|gif|bmp)'
    content = re.sub(pattern2, '', content, flags=re.IGNORECASE)
    content = content.replace('\n', ' ').strip()
    content = re.sub(r'\s+', ' ', content)
    if len(content) < 50:
        return None
    return content
