# Algorithm Unit Tests

Tests are organized to mirror `LazyRAG/algorithm`:

- `chat/`
- `lazyllm/`
- `parsing/`
- `processor/`

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

- `processor/db`: Pure functions, no mocks.
- `chat`: Component and pipeline regression tests.
- `parsing` / `processor`: Service-heavy parts should prefer integration tests or docker-compose.
