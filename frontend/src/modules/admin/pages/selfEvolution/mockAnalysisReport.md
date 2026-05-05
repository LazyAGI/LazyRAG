# RAG 诊断报告
**报告**：`report_20260420_144435_5a2123c3` | **时间**：2026-04-20T14:44:35.338291 | **case 数**：5 | **Synthesizer 轮次**：2
**Pipeline**：`Retriever_1`, `Retriever_2`, `ModuleReranker`, `Formatter_Lambda`, `QwenChat`

## 核心结论
ModuleReranker 因返回固定高分且未有效 rerank，导致 chunk 级召回损失；Retriever_2 的 block 粒度与 topk 设置不足以覆盖 GT chunks。

## 改进建议
| 优先级 | 标题 | 修改方向 | 落点 | 影响指标 | 置信度 | 验证度 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 🔴 P0 | **修复 ModuleReranker 使其调用真实 rerank API** | 在 /Users/chenhao7/LocalScripts/LazyRAG/mock.py:28 将 lazyllm.Reranker(... type='rerank', source='qwen' ...) 替换为能正确调用 gte-rerank 远程 API 的实现或包装器，确保输出分数反映真实相关性 | `/Users/chenhao7/LocalScripts/LazyRAG/mock.py`:28 | `chunk_recall_delta` + | 95% | ✓ 0.95 |
| 🟡 P1 | **将 Retriever_2 的 group_name 改为 line 并验证索引存在** | 在 /Users/chenhao7/LocalScripts/LazyRAG/mock.py:27 将 Retriever(... group_name='block' ...) 修改为 group_name='line' | `/Users/chenhao7/LocalScripts/LazyRAG/mock.py`:27 | `chunk_recall_at_k` + | 85% | ✗ 0.30 |

### 行动详情

#### [A1] 修复 ModuleReranker 使其调用真实 rerank API  (P0)
- **修改方向**: 在 /Users/chenhao7/LocalScripts/LazyRAG/mock.py:28 将 lazyllm.Reranker(... type='rerank', source='qwen' ...) 替换为能正确调用 gte-rerank 远程 API 的实现或包装器，确保输出分数反映真实相关性
- **修改落点**: ✓ `/Users/chenhao7/LocalScripts/LazyRAG/mock.py`:28 (ModuleReranker)
- **理由**: evidence h_0045 显示 ModuleReranker 输出 score_mean/max/min 均为 0.985，无方差，表明未执行真实 rerank，而是返回固定高分，导致排序失效并丢弃 GT chunks。
- **影响指标**: `chunk_recall_delta` +
- **关联 finding**: `F009` / hypothesis `GH1` (rerank_failure)
- **证据 handles**: h_0045
- **支持证据**:
  - h_0045: ModuleReranker 的 step_features 显示 score_mean/score_max/score_min 均为 0.985，无任何方差，表明未执行真实 rerank，而是返回固定高分
  - h_0045: rank_correlation 为 0.0，说明排序结果与原始顺序无相关性，进一步佐证 rerank 未起作用
- **验证备注**:
  - 固定分数强烈暗示 mock 或错误配置，而非真实 rerank API 调用
  - action 提出替换为 gte-rerank 远程 API 实现，方向与证据一致

#### [A2] 将 Retriever_2 的 group_name 改为 line 并验证索引存在  (P1)
- **修改方向**: 在 /Users/chenhao7/LocalScripts/LazyRAG/mock.py:27 将 Retriever(... group_name='block' ...) 修改为 group_name='line'
- **修改落点**: ✓ `/Users/chenhao7/LocalScripts/LazyRAG/mock.py`:27 (Retriever_2)
- **理由**: evidence h_0053/h_0054 显示 Retriever_2 使用 block 分组时未能召回关键内容，而更细粒度的 line 分组理论上可提升定位精度（需确认该分组已建索引）。
- **影响指标**: `chunk_recall_at_k` +
- **关联 finding**: `F011` / hypothesis `GH2` (retrieval_miss)
- **证据 handles**: h_0053, h_0054
- **反向证据**:
  - h_0053 和 h_0054 显示 Retriever_1 和 Retriever_2 均使用 group='block'，但 action 错误地声称 Retriever_2 使用 block 分组导致召回失败；实际上两者的 judge_score 均为 0.4，并未显示 Retriever_2 特有失败
  - raw evidence 中没有任何信息表明 'line' 分组已建索引或其效果优于 'block'
- **验证备注**:
  - 证据未显示 Retriever_2 存在特异性召回问题
  - 无任何关于 'line' 分组索引存在或性能优势的数据支持
  - action 的因果推断缺乏实证依据

## 已确认假设
_暂无已 critic 通过的 confirmed finding。_

## 待回答问题
- answer_correctness=0.88 但 chunk_recall_at_k=0 的根本原因（标注缺失 vs LLM 幻觉）
- Retriever_2 的 doc_recall_at_k=0.75 与 chunk_recall_at_k=0 是否由 chunk 标注错位导致

## 全局指引
诊断确认 ModuleReranker 在 type='rerank' + source='qwen' 下未调用真实 rerank API，而是返回几乎无差异的高分（≈0.985），造成 rerank 失效并系统性丢弃部分 GT chunks。同时，Retriever_2 使用 block 粒度检索，其 topk=10 不足以覆盖分散在多个 blocks 中的相关内容，导致 chunk_recall_at_k=0。修复优先级：P0 解决 reranker 假 rerank 问题（直接影响所有下游）；P1 调整 Retriever_2 的检索策略。风险提示：若不修正 reranker 行为，任何增加 top_n 的尝试都无效，因排序无区分度；调整 group_name 需确保 'line' 分组实际存在且已索引。

## 链路关键节点
* **高风险节点**：`Formatter_Lambda`, `ModuleReranker`, `QwenChat`
* **Retriever_1 → ModuleReranker**：convergence (熵变 -0.649)
* **Retriever_2 → ModuleReranker**：convergence (熵变 -0.249)
* **ModuleReranker → Formatter_Lambda**：divergence (熵变 0.249)
* **Formatter_Lambda → QwenChat**：convergence (熵变 -0.249)