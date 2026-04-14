from __future__ import annotations

from automation.opencode_adapter.events import extract_error_event, extract_text, parse_event_stream
from automation.opencode_adapter.executor import build_change_summary
from automation.opencode_adapter.prompt import build_prompt


def test_build_prompt_contains_constraints() -> None:
    prompt = build_prompt(
        task_plan={'task_id': 'T001', 'goal': 'update target'},
        code_context={'target_file': 'target.txt', 'related_files': ['related.txt']},
        allowlist=['target.txt', 'related.txt'],
    )

    assert 'Only modify files in this allowlist' in prompt
    assert '- target.txt' in prompt
    assert '- related.txt' in prompt
    assert 'Do not run code review, tests, AB tests, or version management tasks.' in prompt


def test_build_prompt_without_allowlist_uses_scope_guidance() -> None:
    prompt = build_prompt(
        task_plan={'task_id': 'T002', 'goal': 'update target'},
        code_context={},
        allowlist=[],
    )

    assert 'No explicit file allowlist was provided.' in prompt
    assert 'Keep changes minimal and tightly scoped to the task plan.' in prompt
    assert 'CodeContext:' in prompt


def test_parse_event_stream_extracts_text_and_errors() -> None:
    events = parse_event_stream(
        '\n'.join(
            [
                '{"type":"step_start","part":{"type":"step-start"}}',
                '{"type":"text","part":{"type":"text","text":"First summary"}}',
                '{"type":"error","error":{"message":"boom"}}',
                '{"type":"text","part":{"type":"text","text":"Second summary"}}',
            ]
        )
    )

    assert extract_text(events) == 'First summary\nSecond summary'
    assert extract_error_event(events) == {'type': 'error', 'error': {'message': 'boom'}}


def test_build_change_summary_counts_lines() -> None:
    summary = build_change_summary(
        ['target.txt'],
        '\n'.join(
            [
                'diff --git a/target.txt b/target.txt',
                '--- a/target.txt',
                '+++ b/target.txt',
                '@@',
                '+new line',
                '-old line',
                '+another line',
            ]
        ),
    )

    assert 'Updated 1 file' in summary
    assert '+2/-1' in summary
