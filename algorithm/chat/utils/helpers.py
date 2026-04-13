import os
from pathlib import Path
from typing import List, Optional, Tuple
from fastapi import HTTPException

from chat.config import MOUNT_BASE_DIR, IMAGE_EXTENSIONS


def validate_and_resolve_files(files: Optional[List[str]]) -> Tuple[List[str], List[str]]:
    if not files:
        return [], []

    root = Path(MOUNT_BASE_DIR).resolve()
    resolved: List[str] = []
    for f in files:
        if '\x00' in f:
            raise HTTPException(status_code=400, detail='Invalid path')
        p = Path(f)
        cand = (p if p.is_absolute() else root / p).resolve()
        if not cand.is_relative_to(root):
            raise HTTPException(status_code=400, detail='Path outside mount directory')
        if not cand.is_file() or not os.access(cand, os.R_OK):
            raise HTTPException(status_code=400, detail=f'File not accessible: {f}')
        resolved.append(str(cand))

    image_files = [p for p in resolved if p.lower().endswith(IMAGE_EXTENSIONS)]
    other_files = [p for p in resolved if p not in image_files]
    return other_files, image_files


def tool_schema_to_string(
    tool_schema: dict,
    include_params: bool = True
) -> str:
    lines = []

    for tool_name, tool_info in tool_schema.items():
        lines.append(f'TOOL NAME: {tool_name}')

        desc = tool_info.get('description')
        if desc:
            lines.append('DESCRIPTION:')
            for sent in desc.split('. '):
                sent = sent.strip()
                if sent:
                    lines.append(f"- {sent.rstrip('.')}.")

        if include_params:
            params = tool_info.get('parameters', {})
            if params:
                lines.append('PARAMETERS:')
                for name, info in params.items():
                    t = info.get('type', 'Any')
                    d = info.get('des', '')
                    lines.append(f'- {name}: {t}' + (f' — {d}' if d else ''))

    return '\n'.join(lines).strip()
