from __future__ import annotations

import json
import textwrap
from typing import Any, Iterable, Mapping


def _dump_block(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def build_prompt(
    task_plan: Mapping[str, Any],
    code_context: Mapping[str, Any],
    allowlist: Iterable[str],
) -> str:
    allowed_files = '\n'.join(f'- {path}' for path in allowlist)
    return textwrap.dedent(
        f"""
        You are editing code inside an isolated git worktree.

        Hard rules:
        1. Make the minimum necessary code change to satisfy the task plan.
        2. Only modify files in this allowlist:
        {allowed_files}
        3. Do not create, rename, or delete files outside the allowlist.
        4. Do not run code review, tests, AB tests, or version management tasks.
        5. Keep behavior changes tightly scoped to the task goal.
        6. End with a concise plain-text change summary in 1-3 sentences.

        TaskPlan:
        {_dump_block(task_plan)}

        CodeContext:
        {_dump_block(code_context)}
        """
    ).strip()
