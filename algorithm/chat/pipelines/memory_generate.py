from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Literal, Optional

from lazyllm import AutoModel
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
    '1. Output only a JSON object; no markdown code blocks, no extra text.\n'
    '2. JSON structure must be {"content": "<new complete text>"}.\n'
    '3. content must be the final complete text after merging all valid input modification requests; do not provide only a patch.\n'  # noqa: E501
)


def _format_inputs_block(
    content: str,
    suggestions: List[Dict[str, Any]],
    user_instruct: Optional[str],
) -> str:
    sections = [
        'Input information:\n'
        '1) Current content (full old text):\n'
        f'{content}\n\n'
    ]

    next_index = 2
    if suggestions:
        sections.append(
            f'{next_index}) suggestions (JSON array; each item may contain an outdated field):\n'
            '- outdated=TRUE means the suggestion is expired and for reference only; ignore if irrelevant to the current modification.\n'  # noqa: E501
            '- outdated=FALSE or missing means the suggestion is still valid and content should be updated accordingly.\n'  # noqa: E501
            f'{json.dumps(suggestions, ensure_ascii=False)}\n\n'
        )
        next_index += 1

    if user_instruct:
        sections.append(
            f'{next_index}) user_instruct (direct user instruction):\n{user_instruct}\n\n'
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
    return f'\nPrevious output was invalid, error: {previous_error}\nPlease correct and regenerate.\n'


def _build_skill_prompt(
    content: str,
    suggestions: List[Dict[str, Any]],
    user_instruct: Optional[str],
    previous_error: Optional[str] = None,
) -> str:
    return (
        'You are a SKILL.md editor. Generate the complete new SKILL.md content based on the input; no explanations or summaries.\n'  # noqa: E501
        'memory type: skill\n'
        'SKILL.md is an abstract SOP (Standard Operating Procedure) that guides the agent to complete tasks '
        'using a unified methodology when the description scope is satisfied.\n'
        '\n'
        '[Format requirements]\n'
        '1. Must start with YAML frontmatter containing at least name and description fields, '
        'followed by a blank line, then the markdown body.\n'
        '2. Keep the existing name value; do not rename unless user_instruct explicitly requests it.\n'
        '3. description should describe the applicable scope and trigger conditions in one sentence; '
        'this is the sole basis for routing/recalling this skill.\n'
        '\n'
        '[Scope and description linkage (important)]\n'
        '- When suggestions or user_instruct involve expanding/narrowing/adjusting the skill scope, trigger scenarios, or coverage, '  # noqa: E501
        'update the frontmatter description accordingly to accurately reflect the new scope.\n'
        '- When changes only affect methodology details in the body without changing the scope, keep description unchanged.\n'  # noqa: E501
        '\n'
        '[Body content rules]\n'
        '- The body must be an abstract SOP: steps, decision criteria, checklists, general rules, output format requirements, etc.\n'  # noqa: E501
        '- Do not include specific cases, project names, specific data, conversation snippets, or one-time examples in the SKILL.md body; '  # noqa: E501
        'if examples are needed, use only highly abstract placeholder illustrations.\n'
        '- If suggestions or user_instruct contain specific cases, abstract the reusable experience into general rules '
        'before writing to the body; do not copy cases verbatim.\n'
        '- Recommended body structure: Applicable conditions / Steps / Judgment & validation / Common pitfalls / Output spec (trim as needed).\n'  # noqa: E501
        '\n'
        '[Length control]\n'
        '- Total length of SKILL.md (including frontmatter) must be within 2000 characters; keep it concise.\n'
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
        'You are an agent memory editor. Generate the complete new memory content based on the input; no explanations or summaries.\n'  # noqa: E501
        'memory type: memory\n'
        'memory stores experience-type content accumulated by the user during usage, such as: problems encountered and solutions, '  # noqa: E501
        'effective practices, lessons learned, domain-specific factual conclusions, preference criteria for certain tasks, etc.\n'  # noqa: E501
        '\n'
        '[Content boundaries]\n'
        '- Only record experience entries with reuse value; do not write one-time logs, pure emotional expressions, or unrelated small talk.\n'  # noqa: E501
        '- Do not record user profile information (identity, role, long-term preferences, communication style, etc.) here; those belong to user_preference.\n'  # noqa: E501
        '- Each experience entry should be self-contained: describe the scenario / approach (or conclusion) / rationale or effect, for easy retrieval and direct use.\n'  # noqa: E501
        '\n'
        '[Writing and merging rules]\n'
        '- Output as plain text full content.\n'
        '- When merging, deduplicate and consolidate: combine same or similar experiences into a more accurate statement; do not stack duplicates.\n'  # noqa: E501
        '- Retain existing valid experiences; experiences explicitly corrected or overridden by suggestions/user_instruct must be updated or deleted.\n'  # noqa: E501
        '- Keep language concise and objective; one experience per line or short paragraph for easy incremental maintenance.\n'  # noqa: E501
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
        'You are a user_preference editor. Generate the complete new user_preference content based on the input; no explanations or summaries.\n'  # noqa: E501
        'memory type: user_preference\n'
        'user_preference stores long-term stable user profile information, such as: user identity / role / domain, '
        'long-term preferences (communication tone, output format, language, level of detail), taboos, common workflow preferences, default context assumptions, etc.\n'  # noqa: E501
        '\n'
        '[Content boundaries]\n'
        '- Only record long-term stable profile information that can be reused in every future interaction.\n'
        '- Do not record specific experiences, specific project knowledge, or one-time events here; those belong to memory.\n'  # noqa: E501
        '- Do not write as chat logs or journals; organize as itemized profile entries that the agent can quickly read.\n'  # noqa: E501
        '\n'
        '[Writing and merging rules]\n'
        '- Output as plain text full content (simple markdown grouping/lists are allowed); no YAML frontmatter.\n'
        '- When merging, update rather than append for the same profile dimension: new preferences override old ones; when conflicting, user_instruct takes precedence.\n'  # noqa: E501
        '- Group by dimension if needed (e.g. identity / output preferences / language & tone / taboos / other conventions).\n'  # noqa: E501
        '- Keep language concise and neutral; no anthropomorphic comments; only state factual user profile entries.\n'
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
        self.llm = AutoModel(model='llm_instruct', config=True)

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
