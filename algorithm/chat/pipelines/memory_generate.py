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
    '输出要求：\n'
    '1. 只能输出 JSON 对象，不要输出 markdown 代码块，不要输出额外文本。\n'
    '2. JSON 结构必须是 {"content": "<新的完整文本>"}。\n'
    '3. content 必须是合并所有有效输入修改要求后的最终完整文本，不能只给 patch。\n'
)


def _format_inputs_block(
    content: str,
    suggestions: List[Dict[str, Any]],
    user_instruct: Optional[str],
) -> str:
    sections = [
        '输入信息如下：\n'
        '1) 当前 content（完整旧文本）：\n'
        f'{content}\n\n'
    ]

    next_index = 2
    if suggestions:
        sections.append(
            f'{next_index}) suggestions（JSON 数组；每条可能包含 outdated 字段）：\n'
            '- outdated 为 TRUE 表示该建议已经过期，仅供参考；若对当前修改无意义，可以忽略。\n'
            '- outdated 为 FALSE 或缺失表示该建议仍有效，需要根据建议修改 content。\n'
            f'{json.dumps(suggestions, ensure_ascii=False)}\n\n'
        )
        next_index += 1

    if user_instruct:
        sections.append(
            f'{next_index}) user_instruct（用户直接指令）：\n{user_instruct}\n\n'
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
    return f'\n上一次输出不合法，错误：{previous_error}\n请修正后重新生成。\n'


def _build_skill_prompt(
    content: str,
    suggestions: List[Dict[str, Any]],
    user_instruct: Optional[str],
    previous_error: Optional[str] = None,
) -> str:
    return (
        '你是一个 SKILL.md 编辑器，根据输入内容生成新的 SKILL.md 全文，不解释、不摘要。\n'
        'memory 类型: skill\n'
        'SKILL.md 是一份抽象的 SOP（标准作业流程），用来指导 agent 在「满足 description 适用范围」时'
        '按照统一方法论完成任务。\n'
        '\n'
        '【格式硬性要求】\n'
        '1. 必须以 YAML frontmatter 开头，frontmatter 至少包含 name 和 description 两个字段，'
        '然后是空行，再是 markdown 正文。\n'
        '2. name 使用已有值，不要随意改名；除非 user_instruct 明确要求改名。\n'
        '3. description 用一句话描述该 skill 的适用范围与触发条件，这是路由/召回这条 skill 的唯一依据。\n'
        '\n'
        '【适用范围与 description 的联动（重要）】\n'
        '- 当 suggestions 或 user_instruct 涉及「扩大 / 缩小 / 调整 skill 的适用范围、触发场景、覆盖对象」时，'
        '必须同步更新 frontmatter 中的 description，使其准确反映新的适用范围。\n'
        '- 当修改仅涉及正文方法论细节、不改变适用范围时，description 保持不变。\n'
        '\n'
        '【正文内容规范】\n'
        '- 正文必须是抽象的 SOP：步骤、判断标准、检查清单、通用规则、输出格式要求等。\n'
        '- 禁止把「具体案例、具体项目名、具体数据、具体对话片段、一次性示例」写进 SKILL.md 正文；'
        '如需举例，只保留高度抽象的占位式示意，不要贴真实案例内容。\n'
        '- 如果 suggestions 或 user_instruct 里带有具体案例，应将其中的**可复用经验**抽象成通用规则，'
        '再写入正文，而不是原样拷贝案例。\n'
        '- 正文结构推荐：适用条件 / 操作步骤 / 判断与校验 / 常见陷阱 / 输出规范，可按需裁剪。\n'
        '\n'
        '【长度控制】\n'
        '- SKILL.md 全文（含 frontmatter）总字数必须控制在 2000 字以内，尽量精炼。\n'
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
        '你是一个 agent memory 编辑器，根据输入内容生成新的 memory 全文，不解释、不摘要。\n'
        'memory 类型: memory\n'
        'memory 用来沉淀「用户在使用过程中积累的经验类内容」，例如：遇到过的问题与解决方案、'
        '行之有效的做法、踩过的坑与教训、领域相关的事实性结论、对某类任务的偏好判断依据等。\n'
        '\n'
        '【内容边界】\n'
        '- 只记录具备复用价值的经验条目；一次性流水账、纯情绪表达、与经验无关的闲聊不要写入。\n'
        '- 不要在此记录用户画像信息（身份、角色、长期偏好、沟通风格等），那些属于 user_preference。\n'
        '- 每条经验尽量自包含：说明「场景 / 做法（或结论）/ 依据或效果」，便于后续被检索和直接使用。\n'
        '\n'
        '【写作与合并规范】\n'
        '- 输出为纯文本全文\n'
        '- 合并时要做去重与归并：相同或相近的经验合成一条更准确的表述，不要堆叠重复项。\n'
        '- 保留原有仍然有效的经验；被 suggestions / user_instruct 明确修正或推翻的经验必须更新或删除。\n'
        '- 语言保持简洁客观，一条经验一行或一小段，便于增量维护。\n'
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
        '你是一个 user_preference 编辑器，根据输入内容生成新的 user_preference 全文，不解释、不摘要。\n'
        'memory 类型: user_preference\n'
        'user_preference 用来沉淀「用户画像」类长期稳定的信息，例如：用户的身份 / 角色 / 所在领域、'
        '长期偏好（沟通语气、输出格式、语言、详略程度）、禁忌项、常用工作流偏好、默认上下文假设等。\n'
        '\n'
        '【内容边界】\n'
        '- 只记录长期稳定、可复用于未来每一次交互的画像信息。\n'
        '- 不要在此记录具体经验、具体项目知识或一次性事件，那些属于 memory。\n'
        '- 不要写成聊天记录或日志；应组织成可被 agent 快速读取的条目化画像。\n'
        '\n'
        '【写作与合并规范】\n'
        '- 输出为纯文本全文（可使用简单 markdown 分组/列表），不要 YAML frontmatter。\n'
        '- 合并时对同一画像维度做更新而非追加：新的偏好覆盖旧的，互相矛盾时以 user_instruct 为准。\n'
        '- 可按维度分组（如：身份 / 偏好输出 / 语言与语气 / 禁忌 / 其他约定）。\n'
        '- 语言简洁中立，不要加入拟人化评论；仅陈述事实性的用户画像条目。\n'
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
