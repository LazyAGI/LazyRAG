# Algorithm Unit Tests

Tests for algorithm modules: common, chat, (parsing/processor require external services).

## Setup

```bash
pip install -r ../../algorithm/requirements.txt
pip install pytest httpx
```

## Run

From project root:

```bash
python -m pytest tests/algorithm/ -v
```

## Strategy

- **common/db**: Pure functions, no mocks.
- **chat**: Tests History/ChatResponse models; full endpoint test requires Document/LLM (or mocks).
- **parsing/processor**: Require Milvus, OpenSearch, DB - use integration tests or docker-compose.
