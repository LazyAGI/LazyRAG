from __future__ import annotations
import logging
import random
import threading
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from evo.datagen.llm import chat
from evo.datagen.prompts import prompt_generate_single_hop
from evo.datagen.validate import normalize_qa_json
from evo.datagen.kb_client import KBClient
from evo.harness.plan import StopRequested

_log = logging.getLogger('evo.datagen.single_hop')


def generate_single_hop(
    ds: KBClient, kb_id: str, algo_id: str, *, count: int, max_workers: int, llm_factory=None, cancel=None
) -> list[dict]:
    if count <= 0:
        return []
    result_list: list[dict] = []
    lock = threading.Lock()
    max_retries = 100
    retry_count = 0
    last_log_percent = 0
    no_doc_flag = False

    def run_single() -> dict | None:
        nonlocal no_doc_flag
        if no_doc_flag or (cancel and cancel()):
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
            valid_chunks = [c for c in chunk_list if len(c.get('content', '')) > 50]
            if not valid_chunks:
                return None
            selected_chunk = random.choice(valid_chunks)
            chunk_id = selected_chunk.get('chunk_id', '')
            prompt = prompt_generate_single_hop(selected_chunk['content'], filename, doc_id, chunk_id)
            try:
                qa_json = chat(prompt, llm_factory=llm_factory)
            except Exception as exc:
                _log.info('llm chat failed: %s', exc)
                qa_json = {}
            qa_json = normalize_qa_json(qa_json)
            if qa_json:
                qa_json['question_type'] = 1
                qa_json['reference_doc'] = [filename]
                qa_json['reference_context'] = [selected_chunk['content']]
                qa_json['reference_doc_ids'] = [doc_id]
                qa_json['reference_chunk_ids'] = [chunk_id]
                return {'qa': qa_json}
            return None
        except Exception as exc:
            _log.error('generate single hop error: %s', exc)
            return None

    executor = ThreadPoolExecutor(max_workers=max_workers)
    try:
        while (
            len(result_list) < count and retry_count < max_retries and (not no_doc_flag) and not (cancel and cancel())
        ):
            tasks = min(max_workers, count - len(result_list))
            futures = {executor.submit(run_single) for _ in range(tasks)}
            while futures:
                if cancel and cancel():
                    raise StopRequested(at_step='case')
                done, _ = wait(futures, timeout=0.2, return_when=FIRST_COMPLETED)
                if not done:
                    continue
                f = done.pop()
                futures.remove(f)
                res = f.result()
                with lock:
                    if no_doc_flag:
                        break
                if res:
                    with lock:
                        if len(result_list) < count:
                            result_list.append(res)
                            current = len(result_list)
                            percent = int(current / count * 100)
                            current_threshold = percent // 25 * 25
                            if current_threshold > last_log_percent:
                                _log.info('single-hop progress: %s/%s (%s%%)', current, count, current_threshold)
                                last_log_percent = current_threshold
                else:
                    with lock:
                        retry_count += 1
            with lock:
                if no_doc_flag:
                    break
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
    _log.info('single-hop done: %s items', len(result_list))
    return result_list


def generate_single_hop_from_chunks(
    chunks: list[dict], *, count: int, max_workers: int, llm_factory=None, cancel=None
) -> list[dict]:
    if count <= 0:
        return []
    rows = list(chunks)
    random.shuffle(rows)
    result_list: list[dict] = []
    lock = threading.Lock()

    def run_one(chunk: dict) -> dict | None:
        if cancel and cancel():
            return None
        prompt = prompt_generate_single_hop(
            chunk['content'], chunk.get('filename', 'unknown'), chunk.get('doc_id', ''), chunk.get('chunk_id', '')
        )
        try:
            qa_json = chat(prompt, llm_factory=llm_factory)
        except Exception as exc:
            _log.info('llm chat failed: %s', exc)
            return None
        qa_json = normalize_qa_json(qa_json)
        if not qa_json:
            return None
        qa_json['question_type'] = 1
        qa_json['reference_doc'] = [chunk.get('filename', 'unknown')]
        qa_json['reference_context'] = [chunk['content']]
        qa_json['reference_doc_ids'] = [chunk.get('doc_id', '')]
        qa_json['reference_chunk_ids'] = [chunk.get('chunk_id', '')]
        return {'qa': qa_json}

    executor = ThreadPoolExecutor(max_workers=max(1, max_workers))
    pending = {}
    iterator = iter(rows[: max(count * 3, count)])

    def submit_next() -> bool:
        if cancel and cancel():
            return False
        try:
            chunk = next(iterator)
        except StopIteration:
            return False
        pending[executor.submit(run_one, chunk)] = chunk
        return True

    try:
        while len(pending) < max(1, max_workers) and submit_next():
            pass
        while pending:
            if cancel and cancel():
                raise StopRequested(at_step='case')
            done, _ = wait(pending, timeout=0.2, return_when=FIRST_COMPLETED)
            if not done:
                continue
            f = done.pop()
            pending.pop(f, None)
            item = f.result()
            if not item:
                continue
            with lock:
                if len(result_list) < count:
                    result_list.append(item)
            if len(result_list) >= count:
                break
            submit_next()
    finally:
        for future in pending:
            future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)
    _log.info('single-hop from chunks done: %s/%s', len(result_list), count)
    return result_list
