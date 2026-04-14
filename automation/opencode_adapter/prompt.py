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
    allowed_files = [str(path) for path in allowlist if str(path).strip()]
    if allowed_files:
        scope_rules = '\n'.join(
            [
                '2. Only modify files in this allowlist:',
                *[f'- {path}' for path in allowed_files],
                '3. Do not create, rename, or delete files outside the allowlist.',
                '4. Avoid unrelated edits, broad refactors, or opportunistic cleanup.',
            ]
        )
    else:
        scope_rules = '\n'.join(
            [
                '2. No explicit file allowlist was provided.',
                '3. Keep changes minimal and tightly scoped to the task plan.',
                '4. Avoid unrelated edits, broad refactors, or opportunistic cleanup.',
            ]
        )
    return textwrap.dedent(
        f"""
        You are editing code inside an isolated git worktree.

        Hard rules:
        1. Make the minimum necessary code change to satisfy the task plan.
        {scope_rules}
        5. Do not run code review, tests, AB tests, or version management tasks.
        6. Keep behavior changes tightly scoped to the task goal.
        7. End with a concise plain-text change summary in 1-3 sentences.

        TaskPlan:
        {_dump_block(task_plan)}

        CodeContext:
        {_dump_block(code_context)}
        """
    ).strip()
