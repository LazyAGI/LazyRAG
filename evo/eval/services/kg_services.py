import json
import networkx as nx
from itertools import combinations
from concurrent.futures import ThreadPoolExecutor, as_completed
from utils.logger import log
from utils.cleaner import clean_and_filter_chunk
from services.chunk_service import get_doc_list, get_all_chunks_with_filename
from config import MAX_PROCESS_CHUNK_PER_DOC, MAX_WORKERS
from services.llm_service import chat
from utils.checker import is_qa_json_valid


class ParallelKGBuilder:
    def __init__(self):
        self.graph = nx.DiGraph()
        self.triple_raw_list = []

    def extract_single_chunk_triples(self, chunk):
        content = chunk["content"]
        filename = chunk["filename"]
        chunk_uid = chunk.get("uid", "")
        doc_id = chunk.get("doc_id", "")
        content = clean_and_filter_chunk(content)
        if not content:
            return [], chunk

        prompt = f"""
你是专业知识图谱抽取专家，只提取核心实体关系，禁止无关描述、时间、形容词、虚词。
严格输出JSON，不要markdown，不要解释。
格式：{{"triples": [{{"subject":"","predicate":"","object":""}}]}}

文本：{content}
"""
        try:
            res = chat(prompt)
            if is_qa_json_valid(res):
                triples = res.get("triples", [])
                return triples, chunk
        except Exception as e:
            log.info(e)
            return [], chunk

    def build_global_graph_from_all_docs(self, kb_id):
        log.info("\n加载全部文档构建全局知识图谱...")
        doc_list = get_doc_list(kb_id)
        log.info(f"总文档数：{len(doc_list)}")

        all_chunks = []
        for idx, doc_item in enumerate(doc_list):
            doc_id = doc_item["doc"]["doc_id"]
            doc_name = doc_item["doc"].get("name", f"{doc_id}")
            log.info(f"读取第 {idx + 1}/{len(doc_list)} 篇：{doc_name}")
            chunks = get_all_chunks_with_filename(kb_id, doc_id)
            chunks = chunks[:MAX_PROCESS_CHUNK_PER_DOC]
            for c in chunks:
                if not c.get("doc_id"):
                    c["doc_id"] = doc_id
            all_chunks.extend(chunks)
            log.info(f"片段数：{len(chunks)}")

        log.info(f"全局总片段数：{len(all_chunks)}")
        log.info("开始并行抽取三元组...")

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_chunk = {executor.submit(self.extract_single_chunk_triples, c): c for c in all_chunks}
            for i, future in enumerate(as_completed(future_to_chunk)):
                triples, chunk = future.result()
                filename = chunk["filename"]
                uid = chunk.get("uid", "")
                doc_id = chunk.get("doc_id", "")
                if i % 20 == 0:
                    log.info(f"进度：{i + 1}/{len(all_chunks)} | {filename}")

                for t in triples:
                    s = t.get("subject", "").strip()
                    p = t.get("predicate", "").strip()
                    o = t.get("object", "").strip()
                    if s and p and o:
                        self.graph.add_node(s)
                        self.graph.add_node(o)
                        self.graph.add_edge(s, o, relation=p)
                        self.triple_raw_list.append({
                            "s": s, "p": p, "o": o,
                            "file": filename,
                            "chunk": chunk,
                            "chunk_uid": chunk.get("uid", ""),
                            "doc_id": chunk.get("doc_id", "")
                        })

        log.info(f"图谱构建完成！节点：{self.graph.number_of_nodes()}，关系：{self.graph.number_of_edges()}")

    def get_triple_source_by_path(self, path):
        source_files = set()
        source_chunks = []
        source_chunk_uids = []
        source_doc_ids = []

        for i in range(len(path) - 1):
            s = path[i]
            o = path[i + 1]
            rel = self.graph[s][o]["relation"]
            for raw in self.triple_raw_list:
                if raw["s"] == s and raw["p"] == rel and raw["o"] == o:
                    source_files.add(raw["file"])
                    source_chunks.append(raw["chunk"])
                    source_chunk_uids.append(raw["chunk_uid"])
                    source_doc_ids.append(raw["doc_id"])
                    break

        is_cross_doc = len(source_files) >= 2
        return {
            "source_files": list(source_files),
            "source_chunks": source_chunks,
            "source_chunk_uids": source_chunk_uids,
            "source_doc_ids": source_doc_ids,
            "is_cross_document": is_cross_doc
        }

    def generate_single_question(self, path):
        try:
            if len(path) != 3:
                return None

            s, bridge, t = path
            left_rel = self.graph[path[0]][path[1]]["relation"]
            right_rel = self.graph[path[1]][path[2]]["relation"]
            desc = f"{s} {left_rel} {bridge} → {bridge} {right_rel} {t}"
            source = self.get_triple_source_by_path(path)

            if not source["is_cross_document"]:
                return None

            c1 = source["source_chunks"][0]["content"]
            c2 = source["source_chunks"][1]["content"]
            cu1 = source["source_chunk_uids"][0] if len(source["source_chunk_uids"]) > 0 else ""
            cu2 = source["source_chunk_uids"][1] if len(source["source_chunk_uids"]) > 1 else ""
            d1 = source["source_doc_ids"][0] if len(source["source_doc_ids"]) > 0 else ""
            d2 = source["source_doc_ids"][1] if len(source["source_doc_ids"]) > 1 else ""

            prompt = f"""
【任务：生成业界标准严格跨文档双跳多跳问题】
请严格遵循以下全部规则，生成自然口语、符合人类日常提问习惯的问题：

1. 以【{bridge}】作为唯一桥梁实体
2. 严格双跳逻辑：片段1 → 桥梁 → 片段2
3. 单独阅读任意一个片段都无法回答
4. ground_truth 只输出极简最终结论
5. 内容严格来自原文，禁止虚构
6. 严禁使用：这个、那个、那份、该项、此类、该份
7. 禁止出现「根据文章、本文、片段、结合资料」
8. 子问题围绕桥梁实体
9. 主问题隐藏桥梁实体，自然连贯
10. key_points 是答题关键点，最多五个，需要根据question和ground_truth提取最核心的关键实体信息，只抽取答案中最核心实体，忽略次要信息，也是一个列表格式


推理路径：{desc}
桥梁实体：{bridge}
片段1：{c1}
片段2：{c2}

严格输出纯JSON：
{{
    "bridge_entity": "{bridge}",
    "sub_question1": "子问题1",
    "sub_question2": "子问题2",
    "question": "双跳问题",
    "ground_truth": "答案",
    "is_single_chunk_unanswerable": true,
    "reason": "双跳逻辑说明",
    "key_points" :"答题关键点"
}}
"""
            try:
                out = chat(prompt)
            except Exception as e:
                log.error(e)
                out = None
            if not out:
                return None
            out = out.replace("```json", "").replace("```", "").strip()
            qa = json.loads(out)

            if not qa.get("is_single_chunk_unanswerable"):
                return None

            res = {
                "question_type": 2,
                "bridge_entity": bridge,
                "path": path,
                "path_detail": desc,
                "sub_question1": qa["sub_question1"],
                "sub_question2": qa["sub_question2"],
                "question": qa["question"],
                "ground_truth": qa["ground_truth"],
                "reference_doc": source["source_files"],
                "reference_context": [c["content"] for c in source["source_chunks"]],
                "reference_chunk_ids": [cu1, cu2],
                "reference_doc_ids": [d1, d2],
                "reason": qa["reason"],
                "key_points": qa["key_points"]
            }

            if not is_valid_real_multihop(res):
                log.info("校验失败：非真实双跳问题，已丢弃")
                return None

            return res

        except Exception as e:
            log.error(f"生成问题失败: {e}")
            return None

    def is_valid_real_multihop(item):
        try:
            question = item["question"]
            chunk1 = item["source_chunks"][0][:800]
            chunk2 = item["source_chunks"][1][:800]

            prompt = f"""
            你是专业严谨的RAG多跳问题评测专家，请严格判断当前问题是否为【合格、可用、自然的跨文档双跳问题】，必须同时满足以下全部条件才输出“是”，否则一律输出“否”：

            判定条件（必须全部满足）：
            1. 仅阅读文档1，完全无法得出答案；
            2. 仅阅读文档2，完全无法得出答案；
            3. 必须同时结合文档1+文档2的信息，串联推理才能回答；
            4. 问题语句通顺自然，符合人类日常真实问答习惯；
            5. 问题不生硬、不奇怪、不机械、无病句、无歧义、无拗口表达；
            6. 问题不含这个、那个、那份、该项等冗余指示代词。

            不符合以上任意一条，一律输出“否”并丢弃该问题。
            禁止输出多余文字、解释、理由，只输出一个字：是 或 否。

            问题：{question}
            文档1：{chunk1}
            文档2：{chunk2}
            """

            try:
                res = chat(prompt)
            except Exception as e:
                log.error(e)
                res = "否"
            return res == "是"
        except Exception as e:
            log.error(f"校验失败: {e}")
            return False

    def generate_multi_hop_questions(self, max_questions=10):
        log.info("开始生成跨文档多跳问题")
        entities = list(self.graph.nodes())
        candidates = []

        for s, t in combinations(entities, 2):
            try:
                path = nx.shortest_path(self.graph, s, t)
                if len(path) == 3:
                    candidates.append(path)
            except:
                continue

        log.info(f"找到候选双跳路径：{len(candidates)}")
        results = []
        generated = set()

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(self.generate_single_question, p) for p in candidates]
            try:
                for f in as_completed(futures):
                    if len(results) >= max_questions:
                        break
                    r = f.result()
                    if r and tuple(r["path"]) not in generated:
                        generated.add(tuple(r["path"]))
                        results.append(r)
                        log.info(f"合格 {len(results)}/{max_questions} | {r['multi_hop_question']}")
            finally:
                executor.shutdown(wait=False, cancel_futures=True)

        log.info(f"生成完成！总计：{len(results)} 条合格双跳问题")
        return results
