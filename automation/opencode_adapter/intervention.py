from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Mapping


HANDOFF_JSON_FILENAME = 'handoff.json'
HANDOFF_MARKDOWN_FILENAME = 'handoff.md'


class LoopFailureSummary:
    def __init__(self, bundle_dir: Path, meta: Mapping[str, Any]) -> None:
        self.bundle_dir = bundle_dir
        self.meta = meta

    def collect_all_artifacts(self) -> Dict[str, Any]:
        attempts = []
        for round_state in self.meta.get('rounds') or []:
            instruction_path = _path_or_none(round_state.get('instruction_path'))
            cli_result_path = _path_or_none(round_state.get('cli_result_path'))
            test_result_path = _path_or_none(round_state.get('test_result_path'))
            test_log_path = _path_or_none(round_state.get('test_log_path'))

            cli_result = _load_json(cli_result_path)
            test_result = _load_json(test_result_path)
            test_log = _read_text(test_log_path)

            cli_payload = cli_result if isinstance(cli_result, dict) else {}
            test_payload = test_result if isinstance(test_result, dict) else {}
            result_payload = cli_payload.get('result') if isinstance(cli_payload.get('result'), dict) else {}
            files_changed = round_state.get('files_changed') or result_payload.get('files_changed') or []

            attempts.append(
                {
                    'round': round_state.get('round'),
                    'instruction': _read_text(instruction_path),
                    'changed_files': list(files_changed) if isinstance(files_changed, list) else [],
                    'change_summary': str(
                        round_state.get('change_summary')
                        or result_payload.get('change_summary')
                        or ''
                    ),
                    'cli_result': cli_result if isinstance(cli_result, dict) else {},
                    'cli_error': round_state.get('cli_error') or cli_payload.get('error'),
                    'test_command': test_payload.get('command') or [],
                    'test_log_summary': _summarize_test_log(test_log),
                    'test_status': str(round_state.get('test_status') or test_payload.get('status') or ''),
                    'repo_copy_dir': str(round_state.get('repo_copy_dir') or ''),
                }
            )

        next_suggestion = _build_next_suggestion(attempts)
        prompt_draft = _build_prompt_draft(
            attempts=attempts,
            next_suggestion=next_suggestion,
            current_repo=str(self.meta.get('current_repo_dir') or ''),
        )
        return {
            'report_id': str(self.meta.get('report_id') or ''),
            'total_rounds': len(attempts),
            'baseline_repo': str(self.meta.get('baseline_repo_dir') or ''),
            'current_repo': str(self.meta.get('current_repo_dir') or ''),
            'attempts': attempts,
            'next_suggestion': next_suggestion,
            'user_prompt_draft': prompt_draft,
        }

    def generate_summary(self) -> str:
        payload = self.collect_all_artifacts()
        lines = [
            '# OpenCode Loop Handoff',
            '',
            f"- Report ID: `{payload['report_id']}`",
            f"- Total rounds: `{payload['total_rounds']}`",
            f"- Baseline repo: `{payload['baseline_repo']}`",
            f"- Current repo: `{payload['current_repo']}`",
            '',
            '## Next Suggestion',
            '',
            payload['next_suggestion'],
            '',
            '## Attempts',
            '',
        ]

        for attempt in payload['attempts']:
            lines.extend(
                [
                    f"### Round {attempt.get('round')}",
                    '',
                    f"- Changed files: `{', '.join(attempt.get('changed_files') or []) or 'none'}`",
                    f"- Change summary: {attempt.get('change_summary') or 'n/a'}",
                    f"- Test status: `{attempt.get('test_status') or 'UNKNOWN'}`",
                    f"- Test log summary: {attempt.get('test_log_summary') or 'n/a'}",
                    '',
                ]
            )

        lines.extend(
            [
                '## Prompt Draft',
                '',
                '```text',
                payload['user_prompt_draft'],
                '```',
                '',
            ]
        )
        return '\n'.join(lines)

    def export_handoff(self) -> Dict[str, Any]:
        payload = self.collect_all_artifacts()
        json_path = self.bundle_dir / HANDOFF_JSON_FILENAME
        md_path = self.bundle_dir / HANDOFF_MARKDOWN_FILENAME
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')
        md_path.write_text(self.generate_summary(), encoding='utf-8')
        return payload


def _path_or_none(path_value: Any) -> Path | None:
    if not path_value:
        return None
    return Path(str(path_value))


def _load_json(path: Path | None) -> Dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    loaded = json.loads(path.read_text(encoding='utf-8'))
    return loaded if isinstance(loaded, dict) else {}


def _read_text(path: Path | None) -> str:
    if path is None or not path.is_file():
        return ''
    return path.read_text(encoding='utf-8').strip()


def _summarize_test_log(log: str) -> str:
    lines = [line.strip() for line in log.splitlines() if line.strip()]
    if not lines:
        return ''

    interesting_tokens = ('AssertionError', 'FAILED', 'ERROR', 'Traceback', 'E   ', 'failed in')
    highlighted = [line for line in lines if any(token in line for token in interesting_tokens)]
    selected = highlighted[-4:] if highlighted else lines[-4:]
    return ' | '.join(selected)


def _build_next_suggestion(attempts: list[dict[str, Any]]) -> str:
    if not attempts:
        return 'Review the report scope and confirm there is at least one editable target before retrying.'

    latest = attempts[-1]
    changed_files = latest.get('changed_files') or []
    if changed_files:
        return (
            'Focus on the latest failing test output and keep the next edit tight around these files: '
            f"{', '.join(changed_files)}."
        )
    return 'The latest attempt did not produce a useful code change. Re-check the prompt and allowed file scope.'


def _build_prompt_draft(
    *,
    attempts: list[dict[str, Any]],
    next_suggestion: str,
    current_repo: str,
) -> str:
    latest = attempts[-1] if attempts else {}
    latest_summary = latest.get('change_summary') or 'No useful code change summary was captured.'
    latest_log = latest.get('test_log_summary') or 'No concise test log summary was captured.'
    return '\n'.join(
        [
            'Continue from the latest attempt history below and keep the edit minimal.',
            f'Current repo copy: {current_repo or "n/a"}',
            f'Latest change summary: {latest_summary}',
            f'Latest test failure summary: {latest_log}',
            f'Next suggestion: {next_suggestion}',
            'Do not widen the scope beyond the allowed files.',
        ]
    )
