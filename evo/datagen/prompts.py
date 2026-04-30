from __future__ import annotations


def prompt_generate_single_hop(context: str, file_name: str, doc_id: str, chunk_id: str) -> str:
    return (
        f'根据文章片段生成1个高质量单跳评测问题，严格输出JSON格式，不要输出任何多余内容。\n'
        f'要求：\n'
        f'1. 必须用原文片段生成问题\n'
        f'2. 问题必须独立完整，禁止出现「根据本段、本文、内容、上文」等指代词汇；\n'
        f'3. 答案必须来自原文，ground_truth 简洁但信息完整；\n'
        f'4. reference_context 填写用到的原始片段原文，需保留这个片段的所有内容；\n'
        f'5. reference_doc 填写参考文章\n'
        f'6. key_points 是答题关键点，最多五个，需要根据question和ground_truth提取最核心的关键实体信息，只抽取答案中最核心实体，忽略次要信息，也是一个列表格式\n'
        f'7. reference_context，reference_doc，key_points一定要是列表格式\n'
        f'8. 严格输出纯JSON，不要任何解释、备注、多余字符。\n'
        f'{{\n'
        f'    "question": "生成的问题",\n'
        f'    "ground_truth": "标准答案",\n'
        f'    "reference_context": ["{context}"],\n'
        f'    "reference_doc": ["{file_name}"],\n'
        f'    "reference_doc_ids": ["{doc_id}"],\n'
        f'    "reference_chunk_ids": ["{chunk_id}"],\n'
        f'    "key_points": ["标准答案答题关键点列表"],\n'
        f'    "generate_reason": "生成逻辑",\n'
        f'    "question_type":1\n'
        f'}}\n'
        f'文本：{context}\n'
        f''
    )


def prompt_generate_table(context: list) -> str:
    context_text = '\n\n'.join(context)
    return (
        f'请从下方文档片段中的表格或类表格结构化数据生成1道评测问题。\n'
        f'\n'
        f'要求：\n'
        f'1. 必须依赖表格的多行/多列信息，优先生成求和、差值、平均值、占比、排序、对比类问题；\n'
        f'2. 禁止只问某个单元格原值，至少需要一次比较或计算；\n'
        f'3. ground_truth 必须包含必要计算过程和最终答案；\n'
        f'4. 问题必须独立完整，禁止出现「根据本段、本文、内容、上表」等指代词汇；\n'
        f'5. key_points 最多五个，只包含判分所需的核心数字、实体或结论；\n'
        f'6. 如果片段内没有可用于出题的表格/类表格数据，输出 {{"skip": true, "reason": "no_table"}}。\n'
        f'7. 严格输出纯JSON，不要任何解释、备注、多余字符。\n'
        f'\n'
        f'固定输出格式：\n'
        f'{{\n'
        f'    "question": "表格推理或计算问题",\n'
        f'    "ground_truth": "计算过程和最终答案",\n'
        f'    "key_points": ["核心判分点"],\n'
        f'    "generate_reason": "生成逻辑",\n'
        f'    "question_type": 4\n'
        f'}}\n'
        f'\n'
        f'文档片段：\n'
        f'{context_text}'
    )


def prompt_generate_list(context: list) -> str:
    context_text = '\n\n'.join(context)
    return (
        f'请从下方文档片段中的列表、条款、步骤、项目符号或编号结构生成1道评测问题。\n'
        f'\n'
        f'要求：\n'
        f'1. 必须依赖列表中的多个条目，优先生成归纳、筛选、排序、条件匹配、差异对比类问题；\n'
        f'2. 禁止只问单个列表项的原文复述，至少需要结合两个条目；\n'
        f'3. ground_truth 必须给出清晰结论，必要时说明匹配或比较依据；\n'
        f'5. 问题必须独立完整，禁止出现「根据本段、本文、内容、上文」等指代词汇；\n'
        f'4. key_points 最多五个，只包含判分所需的核心实体或结论；\n'
        f'5. 如果片段内没有列表/条款/步骤结构，输出 {{"skip": true, "reason": "no_list"}}。\n'
        f'6. 严格输出纯JSON，不要任何解释、备注、多余字符。\n'
        f'\n'
        f'固定输出格式：\n'
        f'{{\n'
        f'    "question": "列表归纳或比较问题",\n'
        f'    "ground_truth": "标准答案",\n'
        f'    "key_points": ["核心判分点"],\n'
        f'    "generate_reason": "生成逻辑",\n'
        f'    "question_type": 5\n'
        f'}}\n'
        f'\n'
        f'文档片段：\n'
        f'{context_text}'
    )


def prompt_generate_formula(context: list) -> str:
    context_text = '\n\n'.join(context)
    return (
        f'请从下方多个文档片段中识别、提取所有数学公式、符号、表达式内容。\n'
        f'基于公式数据生成**1道公式直接代入计算题（单跳即可，无需多跳推理）**。\n'
        f'\n'
        f'要求：\n'
        f'1. 直接提取原文公式，进行简单数值代入计算即可，**不需要两步及以上多跳推理**；\n'
        f'2. 题型为公式代入求值、简单换算类题目；\n'
        f'3. ground_truth必须包含原始公式+代入计算过程+最终结果；\n'
        f'4. reference_context粘贴用到的原文公式片段；\n'
        f'5. 问题必须独立完整，禁止出现「根据本段、根据本文、根据内容」这类指代词汇；\n'
        f'6. 严格输出纯JSON，无任何解释、备注、多余文字。\n'
        f'\n'
        f'固定输出格式：\n'
        f'{{\n'
        f'    "query": "公式代入计算问题",\n'
        f'    "ground_truth": "原始公式+代入计算过程+最终答案",\n'
        f'    "reference_context": "用到的原文公式片段"\n'
        f'}}\n'
        f'\n'
        f'文档片段列表：\n'
        f'{context_text}'
    )


def prompt_evaluate(question, ground_truth, answer, key_points, retrieve_contexts):
    return (
        f'作为专业评测助手，请根据问题、标准答案对模型回答进行准确性和忠实度评分。\n'
        f'## 评测要素\n'
        f'- 问题：{question}\n'
        f'- 标准答案：{ground_truth}\n'
        f'- 模型回答：{answer}\n'
        f'- 答题关键点：{key_points}\n'
        f'- 模型召回的上下文：{retrieve_contexts}\n'
        f'\n'
        f'## 准确性评分核心规则（仅执行，不解释）\n'
        f'1. 关键点判定：仅看人名/地名/数字等事实信息，忽略修饰词，同义词、简写等效（如“公元701年”与“701年”算匹配）。\n'
        f'2. answer_correctness 必须是 0.0~1.0 的小数比例：命中关键点数 / 关键点总数。\n'
        f'3. 全部关键点命中输出 1.0；全部未命中、拒答、无法确定或正确错误信息混合输出 0.0。\n'
        f'4. 多答非预设关键点不扣分；某关键点错误则该点计 0。\n'
        f'\n'
        f'## 参考示例（仅看结果，禁止模仿分析逻辑）\n'
        f'| 关键点总数 | 正确数 | answer_correctness | 理由示例 |\n'
        f'|------------|--------|--------------------|----------|\n'
        f'| 4 | 4 | 1.0 | 全部4个关键点匹配成功 |\n'
        f'| 4 | 0 | 0.0 | 无关键点匹配，答案完全错误 |\n'
        f'| 4 | 2 | 0.5 | 命中2/4个关键点 |\n'
        f'| 3 | 2 | 0.67 | 命中2/3个关键点 |\n'
        f'\n'
        f'## 绝对禁止（违反则评测无效）\n'
        f'1. 禁止输出“好的”“首先”“接下来”等任何前置/后置文字\n'
        f'2. 禁止输出关键点核对步骤、规则推导、分析过程\n'
        f'3. 禁止复制示例格式，仅输出JSON内容\n'
        f'4. 输出内容**仅限标准JSON**，无任何前置、后置文字（包括“好的”“首先”等）。\n'
        f'5. 禁止输出思考过程、分析步骤、规则引用等额外内容。\n'
        f'6. reason字段**控制在100字内**，说明判定依据、扣分原因；defect字段控制在80字内，结合评分、扣分原因简单分析RAG系统扣分可能的潜在缺陷（如召回率低、过度生成等）。\n'
        f'\n'
        f'输出严格JSON格式，不要输出任何多余内容：\n'
        f'{{\n'
        f'    "answer_correctness": 关键点得分（0.0~1.0）,\n'
        f'    "is_correct": true/false,\n'
        f'    "reason": "评分理由",\n'
        f'    "faithfulness": 0.0~1.0\n'
        f'}}\n'
        f''
    )


def prompt_is_real_multihop(question, chunk1, chunk2):
    return (
        f'你是专业严谨的RAG多跳问题评测专家，请严格判断当前问题是否为【合格、可用、自然的跨文档双跳问题】。\n'
        f'必须同时满足以下全部条件才输出“是”，否则一律输出“否”：\n'
        f'\n'
        f'判定条件：\n'
        f'1. 仅阅读文档1，完全无法得出答案；\n'
        f'2. 仅阅读文档2，完全无法得出答案；\n'
        f'3. 必须同时结合文档1+文档2的信息，串联推理才能回答；\n'
        f'4. 语句通顺自然，符合人类日常问答；\n'
        f'5. 问题不生硬、无病句、无歧义；\n'
        f'6. 不含“这个、那个、那份、该项”等冗余代词。\n'
        f'\n'
        f'不符合任意一条，输出“否”。\n'
        f'只输出一个字：是 或 否。\n'
        f'\n'
        f'问题：{question}\n'
        f'文档1：{chunk1}\n'
        f'文档2：{chunk2}\n'
        f''
    )


def prompt_extract_graph(content):
    return (
        f'你是专业知识图谱抽取专家，只提取核心实体关系，禁止无关描述、形容词、虚词。\n'
        f'严格输出JSON，不要markdown，不要解释。\n'
        f'\n'
        f'格式：\n'
        f'{{"triples": [{{"subject":"","predicate":"","object":""}}]}}\n'
        f'\n'
        f'文本：{content}\n'
        f''
    )


def prompt_generate_multihop(bridge_entity, path_desc, chunk1, chunk2):
    return (
        f'【任务：生成业界标准严格跨文档双跳多跳问题】\n'
        f'请严格遵循规则，生成自然、口语化、符合人类习惯的问题：\n'
        f'\n'
        f'1. 以【{bridge_entity}】为唯一桥梁实体；\n'
        f'2. 严格双跳：片段1 → 桥梁 → 片段2；\n'
        f'3. 单独一个片段无法回答，必须结合两个；\n'
        f'4. ground_truth 只输出极简结论；\n'
        f'5. 内容完全来自原文，不虚构；\n'
        f'6. 严禁使用：这个、那个、那份、该项、此类、该份；\n'
        f'7. 禁止出现“根据文章、本文、片段”等官方话术；\n'
        f'8. 子问题围绕桥梁实体；\n'
        f'9. 主问题自然融合，隐藏桥梁实体。\n'
        f'\n'
        f'推理路径：{path_desc}\n'
        f'桥梁实体：{bridge_entity}\n'
        f'片段1：{chunk1}\n'
        f'片段2：{chunk2}\n'
        f'\n'
        f'严格输出纯JSON：\n'
        f'{{\n'
        f'    "bridge_entity": "{bridge_entity}",\n'
        f'    "sub_question1": "子问题1",\n'
        f'    "sub_question2": "子问题2",\n'
        f'    "multi_hop_question": "双跳问题",\n'
        f'    "ground_truth": "答案",\n'
        f'    "is_single_chunk_unanswerable": true,\n'
        f'    "reason": "双跳逻辑说明"\n'
        f'}}\n'
        f''
    )
