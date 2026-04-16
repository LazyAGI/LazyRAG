from __future__ import annotations

import stat
import sys
from pathlib import Path

import pytest


_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


FAKE_OPENCODE_SCRIPT = """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path


def emit(payload):
    print(json.dumps(payload, ensure_ascii=False))


mode = os.environ.get("FAKE_OPENCODE_MODE", "success_modify")
summary = os.environ.get(
    "FAKE_OPENCODE_SUMMARY",
    "Updated the requested files.",
)
auth_count = int(os.environ.get("FAKE_OPENCODE_AUTH_COUNT", "1"))

if len(sys.argv) >= 3 and sys.argv[1:3] == ["auth", "list"]:
    print(f"{auth_count} credentials")
    sys.exit(0)

if len(sys.argv) >= 2 and sys.argv[1] == "run":
    target = os.environ.get("FAKE_OPENCODE_TARGET", "target.txt")
    outside = os.environ.get("FAKE_OPENCODE_OUTSIDE", "outside.txt")
    prompt = sys.argv[-1] if sys.argv else ""
    target_path = Path.cwd() / target
    outside_path = Path.cwd() / outside
    if mode == "success_modify":
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(
            target_path.read_text(encoding="utf-8") + "\\nupdated\\n",
            encoding="utf-8",
        )
        emit({"type": "step_start", "part": {"type": "step-start"}})
        emit({"type": "text", "part": {"type": "text", "text": summary}})
        emit(
            {
                "type": "step_finish",
                "part": {"type": "step-finish", "reason": "stop"},
            }
        )
        sys.exit(0)
    if mode == "no_change":
        emit({"type": "step_start", "part": {"type": "step-start"}})
        emit({"type": "text", "part": {"type": "text", "text": summary}})
        emit(
            {
                "type": "step_finish",
                "part": {"type": "step-finish", "reason": "stop"},
            }
        )
        sys.exit(0)
    if mode == "modify_after_test_failure":
        emit({"type": "step_start", "part": {"type": "step-start"}})
        if "TEST FAILURE LOG:" in prompt:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(
                target_path.read_text(encoding="utf-8") + "\\nupdated\\n",
                encoding="utf-8",
            )
            emit({"type": "text", "part": {"type": "text", "text": summary}})
        else:
            emit(
                {
                    "type": "text",
                    "part": {
                        "type": "text",
                        "text": "Waiting for test feedback.",
                    },
                }
            )
        emit(
            {
                "type": "step_finish",
                "part": {"type": "step-finish", "reason": "stop"},
            }
        )
        sys.exit(0)
    if mode == "scope_violation":
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(
            target_path.read_text(encoding="utf-8") + "\\nupdated\\n",
            encoding="utf-8",
        )
        outside_path.parent.mkdir(parents=True, exist_ok=True)
        outside_path.write_text("out-of-scope\\n", encoding="utf-8")
        emit({"type": "text", "part": {"type": "text", "text": summary}})
        emit(
            {
                "type": "step_finish",
                "part": {"type": "step-finish", "reason": "stop"},
            }
        )
        sys.exit(0)
    if mode == "exec_error":
        emit({"type": "error", "error": {"message": "fake failure"}})
        sys.exit(1)

print(
    json.dumps(
        {"type": "error", "error": {"message": f"unknown mode: {mode}"}}
    )
)
sys.exit(1)
"""


@pytest.fixture
def fake_opencode(tmp_path: Path) -> str:
    script_path = tmp_path / 'fake_opencode.py'
    script_path.write_text(FAKE_OPENCODE_SCRIPT, encoding='utf-8')
    script_path.chmod(script_path.stat().st_mode | stat.S_IEXEC)
    return str(script_path)
