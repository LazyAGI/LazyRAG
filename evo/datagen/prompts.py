from __future__ import annotations


def prompt_generate_single_hop(context: str, file_name: str, doc_id: str, chunk_id: str) -> str:
    return f"""根据文章片段生成1个单跳问题，严格输出JSON格式，不要输出任何多余内容。
要求：
1. 必须用原文片段生成问题，问题需要根据加一些限定条件（如时间、地点、人物等）来限定答案范围，禁止直接摘抄原文内容作为问题；
2. 问题必须独立完整，禁止出现「根据本段、本文、内容、上文」等指代词汇，答案尽量简短；
3. generate_reason 必须写明完整生成逻辑；
4. reference_context 填写用到的原始片段原文，需保留这个片段的所有内容；
5. reference_doc 填写参考文章
6. key_points 是答题关键点，最多五个，需要根据question和ground_truth提取最核心的关键实体信息，只抽取答案中最核心实体，忽略次要信息，也是一个列表格式
7. reference_context，reference_doc，key_points一定要是列表格式
8. 严格输出纯JSON，不要任何解释、备注、多余字符。
{{
    "question": "生成的问题",
    "ground_truth": "标准答案",
    "reference_context": ["{context}"],
    "reference_doc": ["{file_name}"],
    "reference_doc_ids": ["{doc_id}"],
    "reference_chunk_ids": ["{chunk_id}"],
    "key_points": ["标准答案答题关键点列表"],
    "generate_reason": "生成逻辑",
    "question_type":1
}}
文本：{context}
"""


def prompt_generate_table(context: str, file_name: str, doc_id: str, chunk_id: str) -> str:
    return f"""根据提供的文本内容生成**1道多跳表格推理计算题**，严格输出JSON格式，不要输出任何多余内容。
要求：
1. 必须经过两步及以上推理计算，禁止直接从表格摘抄答案；
2. 题型为求和、差值、平均值、占比、对比、排序等数学计算题；
3. 问题必须独立完整，禁止出现「根据本段、本文、内容、上文」等指代词汇；
4. ground_truth 推理出的最终答案必须是一个具体数值
5. reference_context 填写本次用到的原始表格片段原文；
6. reference_doc 填写参考文章
7. key_points 是答题关键点，最多五个，需要根据question和ground_truth提取最核心的关键实体信息，只抽取答案中最核心实体，忽略次要信息，也是一个列表格式
8. reference_context，reference_doc，key_points一定要是列表格式
9. 严格输出纯JSON，不要任何解释、备注、多余字符。
{{
    "question": "生成的问题",
    "ground_truth": "标准答案",
    "reference_context": ["{context}"],
    "reference_doc": ["{file_name}"],
    "reference_doc_ids": ["{doc_id}"],
    "reference_chunk_ids": ["{chunk_id}"],
    "key_points": ["标准答案答题关键点列表"],
    "generate_reason": "生成逻辑",
    "question_type":4
}}
文本：{context}
"""


def prompt_generate_formula(context: str, file_name: str, doc_id: str, chunk_id: str) -> str:
    return f"""请从提供的文本中识别、提取所有数学公式、符号、表达式内容，基于公式数据生成**1道公式直接代入计算题（单跳即可，无需多跳推理）**。
要求：
1. 直接提取原文公式，进行简单数值代入计算即可，**不需要两步及以上多跳推理**；
2. 题型为公式代入求值、简单换算类题目；
3. ground_truth 必须是由原始公式和计算过程共同推理得到的最终结果，答案尽量简短
3. generate_reason 必须写明完整生成逻辑；
4. reference_context 填写用到的原始片段原文，需保留这个片段的所有内容；
5. reference_doc 填写参考文章
6. key_points 是答题关键点，最多五个，需要根据question和ground_truth提取最核心的关键实体信息，只抽取答案中最核心实体，忽略次要信息，也是一个列表格式
7. reference_context，reference_doc，key_points一定要是列表格式
8. 严格输出纯JSON，不要任何解释、备注、多余字符。
{{
    "question": "生成的问题",
    "ground_truth": "标准答案",
    "reference_context": ["{context}"],
    "reference_doc": ["{file_name}"],
    "reference_doc_ids": ["{doc_id}"],
    "reference_chunk_ids": ["{chunk_id}"],
    "key_points": ["标准答案答题关键点列表"],
    "generate_reason": "生成逻辑",
    "question_type":5
}}
文本：{context}
"""


def prompt_evaluate(question, ground_truth, answer, key_points, retrieve_contexts):
    return f"""作为专业评测助手，请根据问题、标准答案对模型回答进行准确性和忠实度评分。
## 评测要素
- 问题：{question}
- 标准答案：{ground_truth}
- 模型回答：{answer}
- 答题关键点：{key_points}
- 模型召回的上下文：{retrieve_contexts}

## 准确性评分核心规则（仅执行，不解释）
1.  关键点判定：仅看人名/地名/数字等事实信息，忽略修饰词，同义词、简写等效（如“公元701年”与“701年”算匹配）。
2.  评分标准（0-5分整数）：
    - 5分=全对（无论关键点总数多少）；4分=对4个；3分=对3个；2分=对2个；1分=对1个
    - 0分=全错/拒答/提示无法确定/正确错误信息混合
3.  补充规则：多答非预设关键点不扣分；某关键点错误则该点计0。

## 参考示例（仅看结果，禁止模仿分析逻辑）
| 关键点总数 | 正确数 | 评分 | 理由示例 |
|------------|--------|------|----------|
| 4 | 4 | 5分 | 全部4个关键点匹配成功 |
| 4 | 0 | 0分 | 无关键点匹配，答案完全错误 |
| 4 | 4 | 5分 | 全匹配，多答内容不扣分 |
| 2 | 2 | 5分 | 2个关键点全对，得满分 |

## 忠实度 faithfulness 评分规则（0.0 ~ 1.0）
1.  定义：忠实度衡量模型回答是否严格基于召回上下文，无幻觉、无编造、无外部知识、无无依据推断。
2.  打分标准：
    - 1.0：完全忠实，所有内容均来自上下文，无幻觉、无编造、无新增事实
    - 0.8：基本忠实，仅少量无关补充，无关键错误与编造
    - 0.5：部分不忠实，轻微脑补/合理推断，无核心事实造假
    - 0.2：明显不忠实，存在关键信息编造、与上下文矛盾
    - 0.0：完全不忠实，通篇幻觉，核心内容与上下文无关或完全冲突

## 忠实度打分示例
- 上下文有明确答案，模型完全引用 → faithfulness = 1.0
- 上下文无相关信息，模型自行编造数据 → faithfulness = 0.0
- 模型部分内容来自上下文，部分自行脑补 → faithfulness = 0.5
- 模型答案与上下文表述矛盾 → faithfulness = 0.2
- 模型多答无关内容但未造假 → faithfulness = 0.8

## 绝对禁止（违反则评测无效）
1. 禁止输出“好的”“首先”“接下来”等任何前置/后置文字
2. 禁止输出关键点核对步骤、规则推导、分析过程
3. 禁止复制示例格式，仅输出JSON内容
4. 输出内容仅限标准JSON，无任何前置、后置文字
5. 禁止输出思考过程、分析步骤、规则引用等额外内容
6. reason字段控制在100字内，说明判定依据、扣分原因

输出严格JSON格式，不要输出任何多余内容：
{{
    "answer_correctness": (关键点得分总和*20)/100,
    "is_correct": true/false,
    "reason": "评分理由",
    "faithfulness": 0.0~1.0
}}
"""


def prompt_is_real_multihop(question, chunk1, chunk2):
    return f"""你是专业严谨的RAG多跳问题评测专家，请严格判断当前问题是否为【合格、可用、自然的跨文档双跳问题】。
必须同时满足以下全部条件才输出“是”，否则一律输出“否”：

判定条件：
1. 仅阅读文档1，完全无法得出答案；
2. 仅阅读文档2，完全无法得出答案；
3. 必须同时结合文档1+文档2的信息，串联推理才能回答；
4. 语句通顺自然，符合人类日常问答；
5. 问题不生硬、无病句、无歧义；
6. 不含“这个、那个、那份、该项”等冗余代词。

不符合任意一条，输出“否”。
只输出一个字：是 或 否。

问题：{question}
文档1：{chunk1}
文档2：{chunk2}
"""


def prompt_extract_graph(content):
    return f"""你是专业知识图谱抽取专家，只提取核心实体关系，禁止无关描述、形容词、虚词。
严格输出JSON，不要markdown，不要解释。

格式：
{{"triples": [{{"subject":"","predicate":"","object":""}}]}}

文本：{content}
"""


def prompt_generate_multihop(bridge_entity, path_desc, chunk1, chunk2):
    return f"""【任务：生成业界标准严格跨文档双跳多跳问题】
请严格遵循规则，生成自然、口语化、符合人类习惯的问题：

1. 以【{bridge_entity}】为唯一桥梁实体；
2. 严格双跳：片段1 → 桥梁 → 片段2；
3. 单独一个片段无法回答，必须结合两个；
4. ground_truth 只输出极简结论；
5. 内容完全来自原文，不虚构；
6. 严禁使用：这个、那个、那份、该项、此类、该份；
7. 禁止出现“根据文章、本文、片段”等官方话术；
8. 子问题围绕桥梁实体；
9. 主问题自然融合，隐藏桥梁实体。

推理路径：{path_desc}
桥梁实体：{bridge_entity}
片段1：{chunk1}
片段2：{chunk2}

严格输出纯JSON：
{{
    "bridge_entity": "{bridge_entity}",
    "sub_question1": "子问题1",
    "sub_question2": "子问题2",
    "multi_hop_question": "双跳问题",
    "ground_truth": "答案",
    "is_single_chunk_unanswerable": true,
    "reason": "双跳逻辑说明"
}}
"""
