from __future__ import annotations
import json
import logging
import re
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from typing import Any
from lazyllm.tracing import current_trace, enable_trace
from evo.datagen.llm import chat
from evo.datagen.prompts import prompt_evaluate
from evo.datagen.trace_context import derive_trace_context, trace_status
from evo.harness.plan import StopRequested

_log = logging.getLogger('evo.datagen.evaluate')


def evaluate_answer(question: str, ground_truth: str, rag_answer: str, key_points: list[str],
                    retrieve_contexts: list[str], *, llm_factory=None,
                    trace_context: dict[str, Any] | None = None,
                    ) -> dict[str, Any]:
    if trace_context:
        expected_trace_id = str(trace_context['trace_id']) if trace_context.get('trace_id') else None
        captured: dict[str, str] = {}

        def _run() -> dict[str, Any]:
            trace = current_trace()
            if trace:
                trace.update_metadata(trace_context)
                captured['trace_id'] = trace.trace_id
            return evaluate_answer(
                question, ground_truth, rag_answer, key_points, retrieve_contexts, llm_factory=llm_factory
            )

        result = enable_trace(
            _run,
            trace_id=expected_trace_id,
            session_id=f"evo:judge:{trace_context.get('report_id', '')}",
            module_trace={'default': True},
        )
        return {
            **result,
            'judge_trace_id': captured.get('trace_id') or expected_trace_id or '',
            'judge_trace_status': trace_status(
                require_trace=True,
                actual_trace_id=captured.get('trace_id', ''),
                expected_trace_id=expected_trace_id,
            ),
        }

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
            return _normalize_eval_result(res)
        raise ValueError(f'invalid eval response: {type(res).__name__}')
    except Exception as exc:
        _log.info('eval parse error: %s', exc)
        return {'answer_correctness': 0, 'is_correct': False, 'reason': 'parse failed', 'faithfulness': 0}


def _parse_json_object(text: str) -> dict[str, Any]:
    text = text.replace('```json', '').replace('```', '').strip()
    try:
        return json.loads(text)
    except Exception:
        match = re.search('\\{.*\\}', text, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group())


def _normalize_eval_result(data: dict[str, Any]) -> dict[str, Any]:
    return {
        'answer_correctness': _score01(data.get('answer_correctness')),
        'is_correct': bool(data.get('is_correct')),
        'reason': str(data.get('reason') or '')[:300],
        'faithfulness': _score01(data.get('faithfulness')),
    }


def _score01(value: Any) -> float:
    score = float(value)
    if score > 1.0 and score <= 5.0:
        score = score / 5.0
    if score < 0.0 or score > 1.0:
        raise ValueError(f'score out of range: {value}')
    return round(score, 4)


def create_evaluate_task(
    eval_queue: list[dict],
    *,
    llm_factory=None,
    max_workers: int = 10,
    on_item=None,
    cancel=None,
    on_progress=None,
    trace_context: dict[str, Any] | None = None,
) -> list[dict]:
    result_list: list[dict] = []
    done = 0
    total = len(eval_queue)
    executor = ThreadPoolExecutor(max_workers=max_workers)
    try:
        pending = {}
        iterator = iter(eval_queue)

        def submit_next() -> bool:
            if cancel and cancel():
                return False
            try:
                item = next(iterator)
            except StopIteration:
                return False
            judge_trace_context = (
                derive_trace_context(trace_context, scene='judge', case_id=str(item.get('case_id') or ''))
                if trace_context is not None
                else None
            )
            pending[executor.submit(
                evaluate_answer,
                item['question'],
                item['ground_truth'],
                item['rag_answer'],
                item.get('key_points', []),
                item.get('retrieve_contexts', []),
                llm_factory=llm_factory,
                trace_context=judge_trace_context,
            )] = item
            return True

        while len(pending) < max_workers and submit_next():
            pass
        while pending:
            if cancel and cancel():
                raise StopRequested(at_step='case')
            done_futures, _ = wait(pending, timeout=0.2, return_when=FIRST_COMPLETED)
            if not done_futures:
                continue
            future = done_futures.pop()
            item = pending.pop(future)
            try:
                evaluate_result = future.result()
            except Exception as exc:
                _log.warning('evaluate task failed: %s', exc)
                evaluate_result = {'error': str(exc)}
            row = {**item, 'evaluate_result': evaluate_result}
            result_list.append(row)
            if on_item:
                on_item(row)
            done += 1
            if on_progress:
                on_progress(done, total)
            submit_next()
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
    return result_list
