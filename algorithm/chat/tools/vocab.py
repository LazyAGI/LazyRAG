import json
from functools import wraps
from typing import Any, Dict, List, Optional

import requests
from lazyllm import LOG, fc_register
from typing_extensions import TypedDict

from chat.tools.memory import _agentic_config, _post_core_api, _session_id
from vocab.db import fetch_vocab_groups_for_create_user_id, resolve_create_user_id_for_session


MAX_VOCAB_SUGGESTIONS_PER_CALL = 5
_WORD_GROUP_APPLY_INTERNAL_PATH = '/inner/word_group:apply'


def _tool_failure(tool_name: str, exc: Exception) -> Dict[str, Any]:
    return {
        'success': False,
        'reason': f'{tool_name} failed: {exc}',
        'error': str(exc),
        'error_type': type(exc).__name__,
    }


def _handle_tool_errors(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            return _tool_failure(func.__name__, exc)

    return wrapper


class VocabSuggestion(TypedDict, total=False):
    """One durable user-specific vocabulary suggestion.

    Fields:
        word (str, required): the first term in the synonym pair.
        synonym (str, required): the matching term the user wants treated as the same concept.
        description (str, optional): the semantic context where this mapping applies.
        reason (str, required): why this mapping is clearly supported by the conversation.
    """

    word: str
    synonym: str
    description: str
    reason: str


def _norm_text(value: Any) -> str:
    return ' '.join(str(value or '').strip().split())


def _norm_key(value: str) -> str:
    return _norm_text(value).casefold()


def _dedupe_keep_order(values: List[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for value in values:
        item = _norm_text(value)
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _resolve_create_user_id(agentic_config: Optional[Dict[str, Any]] = None) -> str:
    config = agentic_config if isinstance(agentic_config, dict) else _agentic_config()
    create_user_id = _norm_text(config.get('create_user_id'))
    if create_user_id:
        return create_user_id

    session_id = _session_id(config)
    return resolve_create_user_id_for_session(session_id)


def _build_memberships(groups: Dict[str, Dict[str, Any]]) -> Dict[str, List[str]]:
    memberships: Dict[str, List[str]] = {}
    for group_id, group in groups.items():
        for word in group.get('words', []):
            key = _norm_key(word)
            memberships.setdefault(key, [])
            if group_id not in memberships[key]:
                memberships[key].append(group_id)
    return memberships


def _serialize_string_list(values: List[str]) -> str:
    return json.dumps(_dedupe_keep_order(values), ensure_ascii=False)


def _plan_action(
    create_user_id: str,
    memberships: Dict[str, List[str]],
    suggestion: VocabSuggestion,
) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, str]]]:
    word = _norm_text(suggestion.get('word'))
    synonym = _norm_text(suggestion.get('synonym'))
    if not word or not synonym or _norm_key(word) == _norm_key(synonym):
        return None, None

    reason = _norm_text(suggestion.get('reason')) or f'User explicitly associated `{word}` with `{synonym}`.'
    description = _norm_text(suggestion.get('description'))
    word_groups = memberships.get(_norm_key(word), [])
    synonym_groups = memberships.get(_norm_key(synonym), [])
    common_groups = sorted(set(word_groups) & set(synonym_groups))

    if common_groups:
        return None, {
            'word': word,
            'synonym': synonym,
            'reason': f'{word} and {synonym} are already covered by existing groups {common_groups}.',
        }

    if word_groups and synonym_groups:
        return None, {
            'word': word,
            'synonym': synonym,
            'reason': f'{word} and {synonym} already exist in different groups and were left unchanged.',
        }

    if not word_groups and not synonym_groups:
        return {
            'reason': reason,
            'words': [word, synonym],
            'description': description,
            'group_ids': _serialize_string_list([]),
            'create_user_id': create_user_id,
            'message_ids': _serialize_string_list([]),
            'action': 'create_new_group',
        }, None

    anchor_groups = word_groups or synonym_groups
    new_word = synonym if word_groups else word
    action = 'add_to_group' if len(anchor_groups) == 1 else 'conflict'
    if action == 'add_to_group':
        memberships.setdefault(_norm_key(new_word), [])
        if anchor_groups[0] not in memberships[_norm_key(new_word)]:
            memberships[_norm_key(new_word)].append(anchor_groups[0])

    return {
        'reason': reason,
        'words': [new_word],
        'description': description,
        'group_ids': _serialize_string_list(list(anchor_groups)),
        'create_user_id': create_user_id,
        'message_ids': _serialize_string_list([]),
        'action': action,
    }, None


@fc_register('tool', execute_in_sandbox=False)
@_handle_tool_errors
def vocab_manage(suggestions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Apply durable user-specific vocabulary updates for the current session user.

    Use this tool only when the conversation clearly establishes a stable term mapping for this user,
    such as the user explicitly saying that A means B, that A should be remembered as B, or that two
    terms should be treated as the same concept in their domain. Do not use it for vague paraphrases,
    general world-knowledge synonyms, temporary nicknames, or one-off wording choices.

    The tool automatically resolves the current session user and updates only that user's vocabulary.
    Pass a small batch of concrete synonym suggestions. Each item must contain exactly one `word`, one
    `synonym`, and a short `reason` grounded in the conversation.

    Args:
        suggestions (List[Dict[str, Any]]): A small batch of stable, user-specific term mappings for
            the current session user. Each item must contain `word`, `synonym`, and `reason`; the
            optional `description` can be used to record the domain context.
    """

    def _ok(result: Dict[str, Any]) -> Dict[str, Any]:
        return {'success': True, 'result': result}

    def _fail(reason: str) -> Dict[str, Any]:
        return {'success': False, 'reason': reason}

    if not suggestions:
        return _fail("'suggestions' must be a non-empty list.")
    if len(suggestions) > MAX_VOCAB_SUGGESTIONS_PER_CALL:
        return _fail(
            f'At most {MAX_VOCAB_SUGGESTIONS_PER_CALL} suggestions are allowed per call; '
            f'got {len(suggestions)}.'
        )

    agentic_config = _agentic_config()
    session_id = _session_id(agentic_config)
    if not session_id:
        return _fail("'session_id' is required in agentic_config.")

    create_user_id = _resolve_create_user_id(agentic_config)
    if not create_user_id:
        return _fail('create_user_id could not be resolved from the current session.')

    groups = fetch_vocab_groups_for_create_user_id(create_user_id)
    memberships = _build_memberships(groups)
    seen_pairs = set()
    actions: List[Dict[str, Any]] = []
    skipped: List[Dict[str, str]] = []

    for suggestion in suggestions:
        word = _norm_text(suggestion.get('word'))
        synonym = _norm_text(suggestion.get('synonym'))
        pair_key = tuple(sorted([_norm_key(word), _norm_key(synonym)]))
        if not word or not synonym or pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)
        action, skipped_item = _plan_action(create_user_id, memberships, suggestion)
        if action is not None:
            actions.append(action)
        elif skipped_item is not None:
            skipped.append(skipped_item)

    result: Dict[str, Any] = {
        'session_id': session_id,
        'create_user_id': create_user_id,
        'submitted_actions': len(actions),
        'skipped': skipped,
    }
    if not actions:
        LOG.info(f'[VocabTool] no-op create_user_id={create_user_id!r} skipped={len(skipped)}')
        return _ok(result)

    payload = {'action_list': actions}
    try:
        result.update(_post_core_api(_WORD_GROUP_APPLY_INTERNAL_PATH, payload))
    except (requests.RequestException, RuntimeError) as exc:
        LOG.error(f'Failed to submit vocab suggestions: {exc}')
        return _fail(f'Failed to submit vocab suggestions: {exc}')

    LOG.info(f'[VocabTool] applied actions={len(actions)} create_user_id={create_user_id!r}')
    return _ok(result)