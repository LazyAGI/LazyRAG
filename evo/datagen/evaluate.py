from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from evo.datagen.llm import chat
from evo.datagen.prompts import prompt_evaluate

_log = logging.getLogger('evo.datagen.evaluate')


def evaluate_answer(
    question: str, ground_truth: str, rag_answer: str,
    key_points: list[str], retrieve_contexts: list[str],
    *, llm_factory=None,
) -> dict[str, Any]:
    kp_str = ', '.join(key_points) if isinstance(key_points, list) else str(key_points)
    rc_str = '\n'.join(retrieve_contexts) if isinstance(retrieve_contexts, list) else str(retrieve_contexts)
    prompt = prompt_evaluate(question, ground_truth, rag_answer, kp_str, rc_str)
    try:
        res = chat(prompt, llm_factory=llm_factory)
        if isinstance(res, list):
            res = res[-1]
        if isinstance(res, str):
            res = _parse_json_object(res)
        if isinstance(res, dict):
            return res
        raise ValueError(f'invalid eval response: {type(res).__name__}')
    except Exception as exc:
        _log.info('eval parse error: %s', exc)
        return {
            'answer_correctness': 0,
            'is_correct': False,
            'reason': 'parse failed',
            'faithfulness': 0,
        }


def _parse_json_object(text: str) -> dict[str, Any]:
    text = text.replace('```json', '').replace('```', '').strip()
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group())


def create_evaluate_task(eval_queue: list[dict], *, llm_factory=None, max_workers: int = 10) -> list[dict]:
    result_list: list[dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(
                evaluate_answer,
                item['question'],
                item['ground_truth'],
                item['rag_answer'],
                item.get('key_points', []),
                item.get('retrieve_contexts', []),
                llm_factory=llm_factory,
            ): item
            for item in eval_queue
        }
        for future in as_completed(future_map):
            item = future_map[future]
            try:
                evaluate_result = future.result()
            except Exception as exc:
                _log.warning('evaluate task failed: %s', exc)
                evaluate_result = {'error': str(exc)}
            result_list.append({**item, 'evaluate_result': evaluate_result})
    return result_list
