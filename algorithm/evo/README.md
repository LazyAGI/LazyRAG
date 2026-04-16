# Evo: LLM-Driven RAG Self-Evolution Analysis System

精简、高效的 RAG 系统诊断与优化框架。

## 核心功能

- **数据加载**: 自动加载和验证评测数据、Trace数据
- **特征工程**: 提取召回、生成、切片等多维度特征
- **统计分析**: 指标统计、相关性分析
- **Agent分析**: 多Agent协作进行深度诊断
- **报告生成**: 自动生成JSON和Markdown诊断报告

## 快速开始

### 1. 配置 API Key

```bash
# 通义千问
export LAZYLLM_QWEN_API_KEY="sk-xxx"

# 或 OpenAI
export LAZYLLM_OPENAI_API_KEY="sk-xxx"

# 或 DeepSeek
export LAZYLLM_DEEPSEEK_API_KEY="sk-xxx"
```

### 2. 运行分析

```bash
cd /Users/chenhao7/LocalScripts/LazyRAG

# 完整分析
PYTHONPATH=. python -m evo.main --full --model=qwen-max

# 交互模式
PYTHONPATH=. python -m evo.main --interactive --model=qwen-max

# 详细日志
PYTHONPATH=. python -m evo.main --full --model=qwen-max --verbose
```

### 3. 查看报告

```bash
cat evo/output/reports/report_*.md
```

## 项目结构

```
evo/
├── agents/              # Agent实现
│   ├── base_agent.py
│   ├── orchestrator_agent.py
│   ├── trace_analyzer_agent.py
│   ├── generate_analyzer_agent.py
│   ├── eval_checker_agent.py
│   ├── diagnose_agent.py
│   └── tool_router_agent.py
├── tools/               # 工具实现
│   ├── data_tools.py
│   ├── feature_tools.py
│   ├── analysis_tools.py
│   ├── stats_tools.py
│   ├── report_tools.py
│   └── visualize_tools.py
├── models/              # 数据模型
│   └── data_models.py
├── session/             # 会话管理
│   └── context.py
├── flow/                # 流程编排
│   └── pipeline.py
├── scripts/             # 脚本
│   ├── setup_env.sh
│   └── quickstart.sh
├── tests/               # 测试
│   └── test_smoke.py
├── data/                # 示例数据
│   ├── judge_mock.json
│   └── trace_mock.json
├── config.py            # 配置管理
├── main.py              # CLI入口
├── lazyllm_shim.py      # LazyLLM兼容层
└── llm_credentials.py   # API Key处理
```

## 支持的模型

| 服务商 | 环境变量 | --model 参数 |
|--------|---------|-------------|
| 通义千问 | `LAZYLLM_QWEN_API_KEY` | `qwen-max` |
| OpenAI | `LAZYLLM_OPENAI_API_KEY` | `gpt-4` |
| DeepSeek | `LAZYLLM_DEEPSEEK_API_KEY` | `deepseek-chat` |

## 命令行参数

```bash
python -m evo.main --full \
  --model=qwen-max \         # 模型名称
  --threshold=0.6 \          # Bad case阈值
  --topk=3 \                 # Top-K分析
  --verbose                  # 详细日志
```

## 运行测试

```bash
PYTHONPATH=. python -m evo.tests.test_smoke
```

## 依赖

```
lazyllm>=0.2.0
numpy>=1.24.0
```

## 常见问题

### "No LLM API key found"

**原因**: 环境变量未设置

**解决**:
```bash
export LAZYLLM_QWEN_API_KEY="your-api-key"
```

### "401 invalid_api_key"

**原因**: API Key无效

**解决**: 检查API Key是否正确

## License

MIT
