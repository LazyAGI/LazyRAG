from __future__ import annotations

import json
import logging
import random
from itertools import combinations
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import networkx as nx

from evo.datagen.clean import clean_and_filter_chunk
from evo.datagen.llm import chat
from evo.datagen.prompts import prompt_extract_graph, prompt_generate_multihop, prompt_is_real_multihop
from evo.datagen.validate import is_qa_json_valid

_log = logging.getLogger('evo.datagen.graph')


class ParallelKGBuilder:
    def __init__(self, *, llm_factory=None, max_workers: int = 10, max_process_chunk_per_doc: int = 80):
        self.graph = nx.DiGraph()
        self.triple_raw_list: list[dict] = []
        self._llm_factory = llm_factory
        self._max_workers = max_workers
        self._max_process_chunk_per_doc = max_process_chunk_per_doc

    def extract_single_chunk_triples(self, chunk: dict) -> tuple[list[dict], dict]:
        content = chunk.get('content', '')
        filename = chunk.get('filename', '')
        chunk_uid = chunk.get('uid', '')
        doc_id = chunk.get('doc_id', '')
        content = clean_and_filter_chunk(content)
        if not content:
            return [], chunk
        prompt = prompt_extract_graph(content)
        try:
            res = chat(prompt, llm_factory=self._llm_factory)
            if is_qa_json_valid(res):
                triples = res.get('triples', [])
                return triples, chunk
        except Exception as exc:
            _log.info('extract triples failed: %s', exc)
        return [], chunk

    def build_global_graph_from_all_docs(self, get_all_chunks_fn) -> None:
        _log.info('build global graph from all docs')
        all_chunks = get_all_chunks_fn()
        random.shuffle(all_chunks)
        all_chunks = all_chunks[:self._max_process_chunk_per_doc]
        _log.info('total chunks: %s', len(all_chunks))
        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            future_to_chunk = {executor.submit(self.extract_single_chunk_triples, c): c for c in all_chunks}
            for i, future in enumerate(as_completed(future_to_chunk)):
                triples, chunk = future.result()
                if i % 20 == 0:
                    _log.info('graph progress: %s/%s', i + 1, len(all_chunks))
                for t in triples:
                    s = t.get('subject', '').strip()
                    p = t.get('predicate', '').strip()
                    o = t.get('object', '').strip()
                    if s and p and o:
                        self.graph.add_node(s)
                        self.graph.add_node(o)
                        self.graph.add_edge(s, o, relation=p)
                        self.triple_raw_list.append({
                            's': s, 'p': p, 'o': o,
                            'file': chunk.get('filename', ''),
                            'chunk': chunk,
                            'chunk_uid': chunk.get('uid', ''),
                            'doc_id': chunk.get('doc_id', ''),
                        })
        _log.info('graph built: nodes=%s edges=%s',
                  self.graph.number_of_nodes(), self.graph.number_of_edges())

    def get_triple_source_by_path(self, path: list[str]) -> dict[str, Any]:
        source_files: set[str] = set()
        source_chunks: list[dict] = []
        source_chunk_uids: list[str] = []
        source_doc_ids: list[str] = []
        for i in range(len(path) - 1):
            s = path[i]
            o = path[i + 1]
            rel = self.graph[s][o]['relation']
            for raw in self.triple_raw_list:
                if raw['s'] == s and raw['p'] == rel and raw['o'] == o:
                    source_files.add(raw['file'])
                    source_chunks.append(raw['chunk'])
                    source_chunk_uids.append(raw['chunk_uid'])
                    source_doc_ids.append(raw['doc_id'])
                    break
        is_cross_doc = len(source_files) >= 2
        return {
            'source_files': list(source_files),
            'source_chunks': source_chunks,
            'source_chunk_uids': source_chunk_uids,
            'source_doc_ids': source_doc_ids,
            'is_cross_document': is_cross_doc,
        }

    def is_valid_real_multihop(self, item: dict) -> bool:
        try:
            question = item['question']
            refs = item.get('reference_context', [])
            if len(refs) < 2:
                return False
            chunk1 = refs[0][:800]
            chunk2 = refs[1][:800]
            prompt = prompt_is_real_multihop(question, chunk1, chunk2)
            try:
                res = chat(prompt, llm_factory=self._llm_factory)
            except Exception as exc:
                _log.error('multihop validation failed: %s', exc)
                res = '否'
            return res == '是'
        except Exception as exc:
            _log.error('validation failed: %s', exc)
            return False

    def generate_single_question(self, path: list[str], cross_doc: bool = True) -> dict | None:
        try:
            if len(path) != 3:
                return None
            s, bridge, t = path
            left_rel = self.graph[path[0]][path[1]]['relation']
            right_rel = self.graph[path[1]][path[2]]['relation']
            desc = f'{s} {left_rel} {bridge} → {bridge} {right_rel} {t}'
            source = self.get_triple_source_by_path(path)
            doc_ids = source.get('source_doc_ids', [])
            chunk_uids = source.get('source_chunk_uids', [])
            if cross_doc:
                if not source['is_cross_document']:
                    return None
                question_type = 3
                log_prefix = '跨文档'
            else:
                if len(set(doc_ids)) != 1:
                    return None
                if len(chunk_uids) < 2 or chunk_uids[0] == chunk_uids[1]:
                    return None
                question_type = 2
                log_prefix = '单文档'
            chunks = source['source_chunks']
            if len(chunks) < 2:
                return None
            c1 = chunks[0]['content']
            c2 = chunks[1]['content']
            cu1 = chunk_uids[0] if len(chunk_uids) > 0 else ''
            cu2 = chunk_uids[1] if len(chunk_uids) > 1 else ''
            d1 = doc_ids[0] if len(doc_ids) > 0 else ''
            d2 = doc_ids[1] if len(doc_ids) > 1 else ''
            prompt = prompt_generate_multihop(bridge, desc, c1, c2)
            try:
                out = chat(prompt, llm_factory=self._llm_factory)
            except Exception as exc:
                _log.error('generate multihop failed: %s', exc)
                return None
            if not out:
                return None
            if isinstance(out, str):
                out = out.replace('```json', '').replace('```', '').strip()
                try:
                    qa = json.loads(out)
                except Exception:
                    return None
            else:
                qa = out
            if not qa.get('is_single_chunk_unanswerable'):
                return None
            res = {
                'question_type': question_type,
                'bridge_entity': bridge,
                'path': path,
                'path_detail': desc,
                'sub_question1': qa.get('sub_question1', ''),
                'sub_question2': qa.get('sub_question2', ''),
                'question': qa.get('multi_hop_question', qa.get('question', '')),
                'ground_truth': qa.get('ground_truth', ''),
                'reference_doc': source['source_files'],
                'reference_context': [c['content'] for c in chunks],
                'reference_chunk_ids': [cu1, cu2],
                'reference_doc_ids': [d1, d2],
                'reason': qa.get('reason', ''),
                'key_points': qa.get('key_points', []),
            }
            if not self.is_valid_real_multihop(res):
                _log.info('validation failed: not real %s multihop', log_prefix)
                return None
            return res
        except Exception as exc:
            _log.error('generate question failed: %s', exc)
            return None

    def generate_multi_hop_questions(self, max_questions: int = 20, cross_doc: bool = True) -> list[dict]:
        if cross_doc:
            _log.info('generate cross-doc multihop questions')
        else:
            _log.info('generate single-doc multihop questions')
        entities = list(self.graph.nodes())
        candidates: list[list[str]] = []
        for s, t in combinations(entities, 2):
            try:
                path = nx.shortest_path(self.graph, s, t)
                if len(path) == 3:
                    candidates.append(path)
            except Exception:
                continue
        _log.info('candidate paths: %s', len(candidates))
        random.shuffle(candidates)
        candidates = candidates[:max(max_questions * 8, max_questions)]
        results: list[dict] = []
        generated: set[tuple] = set()
        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            futures = [executor.submit(self.generate_single_question, p, cross_doc) for p in candidates]
            try:
                for f in as_completed(futures):
                    if len(results) >= max_questions:
                        break
                    r = f.result()
                    if r and tuple(r['path']) not in generated:
                        generated.add(tuple(r['path']))
                        results.append(r)
                        _log.info('qualified %s/%s | %s', len(results), max_questions, r['question'])
            finally:
                executor.shutdown(wait=False, cancel_futures=True)
        _log.info('multihop done: %s questions', len(results))
        return results
