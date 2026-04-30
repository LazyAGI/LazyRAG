from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from evo.runtime.session import AnalysisSession
from evo.tools.io import write_artifact
def write_report_bundle(session: AnalysisSession, payload: dict[str, Any], markdown: str | None, base_name: str) -> dict[str, Path | None]:
    json_text = json.dumps(payload, ensure_ascii=False, indent=2)
    json_info = write_artifact(relpath=f'{base_name}.json', content=json_text).unwrap()
    json_path = Path(json_info['path'])
    session.add_artifact('report', json_path)
    md_path: Path | None = None
    if markdown:
        md_info = write_artifact(relpath=f'{base_name}.md', content=markdown).unwrap()
        md_path = Path(md_info['path'])
        session.add_artifact('markdown', md_path)
    return {'json_path': json_path, 'markdown_path': md_path}
