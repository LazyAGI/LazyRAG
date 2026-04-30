from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Literal, Optional

from chat.pipelines.builders.get_models import get_automodel
from chat.tools.skill_manager import _validate_skill_content

MemoryType = Literal['skill', 'memory', 'user_preference']

_MAX_GENERATE_ATTEMPTS = 3
_JSON_BLOCK_RE = re.compile(r'```json\s*(.*?)\s*```', re.DOTALL)
_THINK_BLOCK_RE = re.compile(r'<think>.*?</think\s*>', re.DOTALL | re.IGNORECASE)


class BadRequestError(ValueError):
    """Raised when request body fields are missing or malformed."""


class UnprocessableContentError(ValueError):
    """Raised when generated content is repeatedly invalid."""


def _normalize_suggestions(raw_suggestions: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    if raw_suggestions is None:
        return []
    if not isinstance(raw_suggestions, list):
        raise BadRequestError("'suggestions' must be an array when provided.")

    normalized: List[Dict[str, Any]] = []
    for idx, item in enumerate(raw_suggestions):
        if not isinstance(item, dict):
            raise BadRequestError(f"'suggestions[{idx}]' must be an object.")

        title = item.get('title')
        content = item.get('content')
        reason = item.get('reason')
        outdated = item.get('outdated')

        if not isinstance(title, str) or not title.strip():
            raise BadRequestError(
                f"'suggestions[{idx}].title' must be a non-empty string."
            )
        if not isinstance(content, str) or not content.strip():
            raise BadRequestError(
                f"'suggestions[{idx}].content' must be a non-empty string."
            )
        if reason is not None and not isinstance(reason, str):
            raise BadRequestError(f"'suggestions[{idx}].reason' must be a string.")
        if outdated is not None and not isinstance(outdated, bool):
            raise BadRequestError(f"'suggestions[{idx}].outdated' must be a boolean.")

        normalized_item: Dict[str, Any] = {
            'title': title.strip(),
            'content': content.strip(),
        }
        if isinstance(reason, str) and reason.strip():
            normalized_item['reason'] = reason.strip()
        if outdated is not None:
            normalized_item['outdated'] = outdated
        normalized.append(normalized_item)
    return normalized


def _extract_json_object(raw: Any) -> Dict[str, Any]:
    text = str(raw).strip()
    text = _THINK_BLOCK_RE.sub('', text).strip()

    match = _JSON_BLOCK_RE.search(text)
    if match:
        text = match.group(1).strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        left = text.find('{')
        right = text.rfind('}')
        if left < 0 or right <= left:
            raise UnprocessableContentError('Model output is not valid JSON.')
        try:
            parsed = json.loads(text[left: right + 1])
        except json.JSONDecodeError as exc:
            raise UnprocessableContentError(
                f'Model output is not valid JSON: {exc}'
            ) from exc

    if not isinstance(parsed, dict):
        raise UnprocessableContentError('Model output must be a JSON object.')
    return parsed


def _validate_generated_content(memory_type: MemoryType, content: Any) -> str:
    if not isinstance(content, str):
        raise UnprocessableContentError("Generated field 'content' must be a string.")

    if memory_type == 'skill':
        validation_error = _validate_skill_content(content)
        if validation_error:
            raise UnprocessableContentError(
                f'Generated SKILL.md is invalid: {validation_error}'
            )
    return content


_COMMON_OUTPUT_SPEC = (
    'Output requirements:\n'
    '1. Output only a JSON object. Do not output a markdown code block or any extra text.\n'
    '2. The JSON object must be {"content": "<new complete text>"}.\n'
    '3. The content field must contain the final complete text after merging all valid change requests; '
    'do not output a patch only.\n'
)


def _format_inputs_block(
    content: str,
    suggestions: List[Dict[str, Any]],
    user_instruct: Optional[str],
) -> str:
    sections = [
        'Input information:\n'
        '1) Current content (complete previous text):\n'
        f'{content}\n\n'
    ]

    next_index = 2
    if suggestions:
        sections.append(
            f'{next_index}) suggestions (JSON array; each item may contain an outdated field):\n'
            '- outdated TRUE means the suggestion is stale and should be treated as reference only; '
            'ignore it if it is not useful for the current edit.\n'
            '- outdated FALSE or missing means the suggestion is still valid and should be applied to content.\n'
            f'{json.dumps(suggestions, ensure_ascii=False)}\n\n'
        )
        next_index += 1

    if user_instruct:
        sections.append(
            f'{next_index}) user_instruct (direct natural-language instruction from the user):\n{user_instruct}\n\n'
        )

    return ''.join(sections)


def _normalize_user_instruct(raw_user_instruct: Any) -> Optional[str]:
    if raw_user_instruct is None:
        return None
    if not isinstance(raw_user_instruct, str):
        raise BadRequestError("'user_instruct' must be a string when provided.")

    normalized = raw_user_instruct.strip()
    return normalized or None


def _format_retry_note(previous_error: Optional[str]) -> str:
    if not previous_error:
        return ''
    return f'\nThe previous output was invalid. Error: {previous_error}\nPlease fix it and regenerate.\n'


def _build_skill_prompt(
    content: str,
    suggestions: List[Dict[str, Any]],
    user_instruct: Optional[str],
    previous_error: Optional[str] = None,
) -> str:
    return (
        'You are a SKILL.md editor. Generate the new complete SKILL.md text from the inputs. '
        'Do not explain or summarize.\n'
        'memory type: skill\n'
        'SKILL.md is an abstract SOP (standard operating procedure) that guides the agent to handle tasks '
        'with a unified methodology when the task falls within the frontmatter description.\n'
        '\n'
        'Language policy: write the generated content in the language implied by '
        'the existing content and the user input. '
        'If the user_instruct explicitly requests Chinese, write Chinese; if it requests English, write English.\n'
        '\n'
        'Hard format requirements:\n'
        '1. The file must start with YAML frontmatter. The frontmatter must contain at least name and description, '
        'followed by a blank line and then the markdown body.\n'
        '2. Keep the existing name by default; do not rename it unless user_instruct explicitly asks for a rename.\n'
        '3. The description must describe in one sentence the scope and trigger conditions of this skill. '
        'It is the only basis for routing/retrieving this skill.\n'
        '\n'
        'Scope-description coupling (important):\n'
        '- If suggestions or user_instruct expands, narrows, or otherwise changes '
        'the applicable scope, trigger scenario, '
        'or covered objects of the skill, update the frontmatter description accordingly.\n'
        '- If the edit only changes methodological details in the body and does not change the applicable scope, '
        'keep the description unchanged.\n'
        '\n'
        'Body requirements:\n'
        '- The body must be an abstract SOP: steps, decision criteria, checklists, '
        'general rules, and output requirements.\n'
        '- Do not write concrete cases, project names, data, conversation snippets, or one-off examples into the body. '
        'If an example is necessary, keep it as a highly abstract placeholder-style illustration.\n'
        '- If suggestions or user_instruct contains concrete cases, extract the reusable lesson and convert it into '
        'a general rule instead of copying the case verbatim.\n'
        '- Recommended sections include applicable conditions, operating steps, '
        'judgment and validation, common pitfalls, '
        'and output requirements. Trim sections as needed.\n'
        '\n'
        'Length control:\n'
        '- Keep the full SKILL.md file, including frontmatter, within 2000 words '
        'or the equivalent length. Be concise.\n'
        '\n'
        f'{_format_retry_note(previous_error)}'
        f'{_format_inputs_block(content, suggestions, user_instruct)}'
        f'{_COMMON_OUTPUT_SPEC}'
    )


def _build_memory_prompt(
    content: str,
    suggestions: List[Dict[str, Any]],
    user_instruct: Optional[str],
    previous_error: Optional[str] = None,
) -> str:
    return (
        'You are an agent memory editor. Generate the new complete memory text from the inputs. '
        'Do not explain or summarize.\n'
        'memory type: memory\n'
        'memory stores reusable experiential knowledge accumulated during use, such as problems and solutions, '
        'effective practices, pitfalls and lessons learned, domain facts, or criteria for a class of tasks.\n'
        '\n'
        'Language policy: write the generated content in the language implied by '
        'the existing content and the user input. '
        'If the user_instruct explicitly requests Chinese, write Chinese; if it requests English, write English.\n'
        '\n'
        'Content boundaries:\n'
        '- Record only reusable experience. Do not store one-off logs, pure emotional '
        'expression, or irrelevant small talk.\n'
        '- Do not store user profile information here, such as identity, role, '
        'long-term preferences, or communication style; '
        'those belong to user_preference.\n'
        '- Each memory item should be as self-contained as possible: describe the scenario, practice or conclusion, '
        'and supporting basis or effect so it can be retrieved and used later.\n'
        '\n'
        'Writing and merging rules:\n'
        '- Output the full plain text content.\n'
        '- Deduplicate and consolidate during merging: combine identical or similar '
        'experiences into a more accurate statement.\n'
        '- Keep existing valid experiences. Update or delete any experience explicitly corrected or invalidated by '
        'suggestions or user_instruct.\n'
        '- Keep the language concise and objective. Prefer one line or one short paragraph per experience for '
        'incremental maintenance.\n'
        '\n'
        f'{_format_retry_note(previous_error)}'
        f'{_format_inputs_block(content, suggestions, user_instruct)}'
        f'{_COMMON_OUTPUT_SPEC}'
    )


def _build_user_preference_prompt(
    content: str,
    suggestions: List[Dict[str, Any]],
    user_instruct: Optional[str],
    previous_error: Optional[str] = None,
) -> str:
    return (
        'You are a user_preference editor. Generate the new complete user_preference text from the inputs. '
        'Do not explain or summarize.\n'
        'memory type: user_preference\n'
        'user_preference stores long-term stable user profile information, such as identity or role, domain, '
        'communication tone, output format, language preference, verbosity preference, taboos, workflow preferences, '
        'and default context assumptions.\n'
        '\n'
        'Language policy: write the generated content in the language implied by '
        'the existing content and the user input. '
        'If the user_instruct explicitly requests Chinese, write Chinese; if it requests English, write English.\n'
        '\n'
        'Content boundaries:\n'
        '- Record only long-term stable profile information that can be reused in future interactions.\n'
        '- Do not record specific experiences, project knowledge, or one-off events here; those belong to memory.\n'
        '- Do not write chat transcripts or logs. Organize the content as profile '
        'entries that the agent can read quickly.\n'
        '\n'
        'Writing and merging rules:\n'
        '- Output the full plain text content. Simple markdown grouping or lists '
        'are allowed; do not use YAML frontmatter.\n'
        '- Update rather than append the same profile dimension. New preferences '
        'override old ones; if there is a conflict, '
        'user_instruct has the highest priority.\n'
        '- Group by dimension when useful, such as identity, output preferences, '
        'language and tone, taboos, and other conventions.\n'
        '- Keep the language concise and neutral. Do not add personified comments; '
        'only state factual user profile entries.\n'
        '\n'
        f'{_format_retry_note(previous_error)}'
        f'{_format_inputs_block(content, suggestions, user_instruct)}'
        f'{_COMMON_OUTPUT_SPEC}'
    )


_PROMPT_BUILDERS = {
    'skill': _build_skill_prompt,
    'memory': _build_memory_prompt,
    'user_preference': _build_user_preference_prompt,
}


def _build_generate_prompt(
    memory_type: MemoryType,
    content: str,
    suggestions: List[Dict[str, Any]],
    user_instruct: Optional[str],
    previous_error: Optional[str] = None,
) -> str:
    try:
        builder = _PROMPT_BUILDERS[memory_type]
    except KeyError as exc:
        raise BadRequestError(f'Unsupported memory type: {memory_type!r}') from exc
    return builder(
        content=content,
        suggestions=suggestions,
        user_instruct=user_instruct,
        previous_error=previous_error,
    )


class MemoryGeneratePipeline:
    def __init__(self) -> None:
        self.llm = get_automodel('llm_instruct')

    def generate(
        self,
        memory_type: MemoryType,
        content: Any,
        suggestions: Optional[List[Dict[str, Any]]],
        user_instruct: Any,
    ) -> str:
        if not isinstance(content, str):
            raise BadRequestError("'content' is required and must be a string.")

        normalized_suggestions = _normalize_suggestions(suggestions)
        normalized_user_instruct = _normalize_user_instruct(user_instruct)
        if not normalized_suggestions and normalized_user_instruct is None:
            raise BadRequestError(
                "At least one of 'suggestions' or 'user_instruct' must be provided."
            )

        error: Optional[str] = None
        for _ in range(_MAX_GENERATE_ATTEMPTS):
            prompt = _build_generate_prompt(
                memory_type=memory_type,
                content=content,
                suggestions=normalized_suggestions,
                user_instruct=normalized_user_instruct,
                previous_error=error,
            )
            raw = self.llm(prompt)
            parsed = _extract_json_object(raw)
            try:
                return _validate_generated_content(memory_type, parsed.get('content'))
            except UnprocessableContentError as exc:
                error = str(exc)

        raise UnprocessableContentError(
            f'Failed to generate valid content after {_MAX_GENERATE_ATTEMPTS} attempts: {error}'
        )


memory_generate_pipeline = MemoryGeneratePipeline()


def generate_memory_content(
    memory_type: MemoryType,
    content: Any,
    suggestions: Optional[List[Dict[str, Any]]],
    user_instruct: Any,
) -> str:
    return memory_generate_pipeline.generate(
        memory_type=memory_type,
        content=content,
        suggestions=suggestions,
        user_instruct=user_instruct,
    )
