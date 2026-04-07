import os
from typing import List, Optional, Tuple
from fastapi import HTTPException

from chat.config import MOUNT_BASE_DIR, IMAGE_EXTENSIONS


def validate_and_resolve_files(files: Optional[List[str]]) -> Tuple[List[str], List[str]]:
    if not files:
        return [], []

    resolved: List[str] = []
    for f in files:
        real_path = f if os.path.isabs(f) else os.path.join(MOUNT_BASE_DIR, f)
        if not (os.path.isfile(real_path) and os.access(real_path, os.R_OK)):
            raise HTTPException(status_code=400, detail=f'File {real_path} is not accessible')
        resolved.append(real_path)

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
                for param_name, param_info in params.items():
                    p_type = param_info.get('type', 'Any')
                    p_desc = param_info.get('des', '')
                    if p_desc:
                        lines.append(
                            f'- {param_name}: {p_type} — {p_desc}'
                        )
                    else:
                        lines.append(
                            f'- {param_name}: {p_type}'
                        )

    return '\n'.join(lines).strip()
