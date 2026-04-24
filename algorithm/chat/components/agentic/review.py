from __future__ import annotations

import os
import threading
import traceback
from typing import Any

import lazyllm
from lazyllm.tools.fs.client import FS

from chat.components.agentic.config import REVIEW_PROMPTS, REVIEW_TOOLS, _env_int
from chat.prompts.agentic_v2 import _COMBINED_REVIEW_PROMPT, _MEMORY_FLUSH_MESSAGES
from chat.tools.skill_manager import list_all_skills_with_category


def _decide_review_mode(
    available_tools: list[str],
    tool_turns: int,
    user_turns: int,
    memory_review_interval: int,
    skill_review_interval: int,
) -> str | None:
    if os.getenv('LAZYRAG_SKILL_REVIEW_DEBUG', '').lower() in ('1', 'true', 'yes'):
        return 'combined'

    memory_due = (
        'memory' in available_tools
        and user_turns > memory_review_interval
    )
    skill_due = (
        'skill_manage' in available_tools
        and tool_turns > skill_review_interval
        and user_turns > 1
    )
    if memory_due and skill_due:
        return 'combined'
    if memory_due:
        return 'memory'
    if skill_due:
        return 'skill'
    return None


def _spawn_background_review(
    config: dict,
    llm: Any,
    sandbox: Any,
    keep_full_turns: int,
    history_snapshot: list,
    review_mode: str,
    request_global_sid: str,
) -> None:
    review_tools = REVIEW_TOOLS.get(review_mode, [])
    review_prompt = REVIEW_PROMPTS.get(review_mode, _COMBINED_REVIEW_PROMPT)
    if not review_tools:
        return

    snapshot = list(history_snapshot)
    skills_dir = config.get('skill_fs_url') or ''
    review_skills = (
        list(list_all_skills_with_category(skills_dir).keys())
        if review_mode in ('skill', 'combined') and skills_dir
        else []
    )

    def _worker() -> None:
        tname = threading.current_thread().name
        print(f'[bg-review:{review_mode}] START thread={tname} sid={request_global_sid}')
        try:
            lazyllm.globals._init_sid(request_global_sid)
            lazyllm.locals._init_sid()
            lazyllm.globals['agentic_config'] = config

            review_agent = lazyllm.tools.agent.ReactAgent(
                llm=llm,
                tools=review_tools,
                max_retries=_env_int('LAZYRAG_REVIEW_MAX_RETRIES', 5),
                return_trace=False,
                prompt=review_prompt,
                skills=review_skills,
                keep_full_turns=keep_full_turns,
                sandbox=sandbox,
                fs=FS,
                skills_dir=skills_dir,
                enable_builtin_tools=True,
                force_summarize=True,
                force_summarize_context=review_prompt,
            )
            res = review_agent(_MEMORY_FLUSH_MESSAGES['session_end'], llm_chat_history=snapshot)
            print(f'[bg-review:{review_mode}] DONE thread={tname}\n{res}')
        except Exception:
            print(f'[bg-review:{review_mode}] FAILED thread={tname}')
            traceback.print_exc()
        finally:
            lazyllm.locals.clear()
            print(f'[bg-review:{review_mode}] EXIT thread={tname}')

    if os.getenv('LAZYRAG_REVIEW_DEBUG', '').lower() in ('1', 'true', 'yes'):
        _worker()
    else:
        thread = threading.Thread(target=_worker, daemon=True)
        print(f'[bg-review:{review_mode}] spawn sid={request_global_sid}')
        thread.start()
