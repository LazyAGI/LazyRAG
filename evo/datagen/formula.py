from __future__ import annotations

import logging
import random
import threading
from concurrent.futures import ThreadPoolExecutor

from evo.datagen.llm import chat
from evo.datagen.prompts import prompt_generate_formula
from evo.datagen.validate import is_qa_json_valid
from evo.datagen.kb_client import KBClient

_log = logging.getLogger('evo.datagen.formula')


def generate_formula_qa(
    ds: KBClient, kb_id: str, algo_id: str,
    *, count: int, max_workers: int, llm_factory=None,
) -> list[dict]:
    result_list: list[dict] = []
    lock = threading.Lock()
    max_retries = 100
    retry_count = 0
    last_log_percent = 0
    no_doc_flag = False

    def run_single() -> dict | None:
        nonlocal no_doc_flag
        if no_doc_flag:
            return None
        try:
            doc_list = ds.get_doc_list(kb_id, algo_id)
            if not doc_list:
                with lock:
                    no_doc_flag = True
                _log.error('no docs in kb, abort')
                return None

            selected_doc = random.choice(doc_list)['doc']
            doc_id = selected_doc['doc_id']
            filename = selected_doc.get('filename', 'unknown.pdf')
            chunk_list = ds.get_chunks(kb_id, doc_id, algo_id)

            formula_chunks = []
            formula_keys = {
                '=', '$', '\\', '+', '-', '*', '/', '×', '÷', '^', '_',
                '公式', '函数', '方程', '系数', '变量', '定理', '计算', '表达式'
            }
            for chunk in chunk_list:
                content = chunk.get('content', '')
                if any(key in content for key in formula_keys):
                    formula_chunks.append(chunk)

            valid_chunks = [c for c in formula_chunks if len(c.get('content', '')) > 50]
            if not valid_chunks:
                return None

            selected_chunk = random.choice(valid_chunks)
            chunk_id = selected_chunk.get('chunk_id', '')

            prompt = prompt_generate_formula(selected_chunk['content'], filename, doc_id, chunk_id)

            try:
                qa_json = chat(prompt, llm_factory=llm_factory)
            except Exception as exc:
                _log.info('llm chat failed: %s', exc)
                qa_json = {}

            if is_qa_json_valid(qa_json):
                qa_json['reference_doc_ids'] = [doc_id]
                qa_json['reference_chunk_ids'] = [chunk_id]
                return {'qa': qa_json}
            return None

        except Exception as exc:
            _log.error('generate formula qa error: %s', exc)
            return None

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        while len(result_list) < count and retry_count < max_retries and not no_doc_flag:
            tasks = min(max_workers, count - len(result_list))
            futures = [executor.submit(run_single) for _ in range(tasks)]
            for f in futures:
                res = f.result()
                with lock:
                    if no_doc_flag:
                        break
                if res:
                    with lock:
                        if len(result_list) < count:
                            result_list.append(res)
                            current = len(result_list)
                            percent = int((current / count) * 100)
                            current_threshold = (percent // 25) * 25
                            if current_threshold > last_log_percent:
                                _log.info('formula-qa progress: %s/%s (%s%%)',
                                          current, count, current_threshold)
                                last_log_percent = current_threshold
                else:
                    with lock:
                        retry_count += 1
            with lock:
                if no_doc_flag:
                    break

    _log.info('formula-qa done: %s items', len(result_list))
    return result_list