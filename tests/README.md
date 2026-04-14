# LazyRAG Tests

Unit tests for five modules: **frontend**, **backend (core)**, **auth-service**, **algorithm**, and **automation**.

## Directory Structure

| Directory | Scope | Framework |
|-----------|-------|-----------|
| `frontend/` | Frontend SPA (vanilla JS) | Vitest + jsdom |
| `backend/auth-service/` | FastAPI auth (JWT, RBAC, users, roles) | pytest + httpx |
| `backend/core/` | Go API (ACL, handlers) | Go testing |
| `algorithm/` | Chat, parsing, processor, common | pytest + unittest.mock |
| `automation/` | Host-side OpenCode adapter | pytest + fake CLI subprocess |

## Dependency Chain & Mock Strategy

```
Frontend → auth-service (JWT) → Kong RBAC → core (ACL) → algorithm
```

| Module | Mocks | Strategy |
|--------|-------|----------|
| **Frontend** | `fetch` | Vitest vi.stubGlobal; test pure functions by loading script in jsdom |
| **auth-service** | DB (SQLite in-memory) | Override `SessionLocal`; no external deps |
| **backend/core** | ACL Store, DB | Interface injection; use sqlite for integration |
| **algorithm** | Document, LLM, Milvus, OpenSearch | `unittest.mock.patch` |
| **automation** | `opencode` CLI | Fake executable + temp git repo |

## One-Click Execution

### Local

```bash
# From project root
./tests/run-all.sh

# Or via Makefile
make test
```

### CI (GitHub Actions)

Workflow: `.github/workflows/ci.yml` (pull_request_target)

**Flow:** lint → doc_check → wait_approve (environment: `protest`) → tests

**Setup:** Create environment `protest` in GitHub: Settings → Environments → New environment → name: `protest`. Add protection rules if you want manual approval before tests run.

## Per-Module Commands

```bash
# Frontend
cd tests/frontend && npm test

# auth-service
cd tests/backend/auth-service && python -m pytest -v

# backend core (Go)
cd tests/backend/core && go test ./...

# Algorithm
cd tests/algorithm && python -m pytest -v
```

## Prerequisites

- **Node.js 18+** (frontend)
- **Python 3.11+** (auth-service, algorithm)
- **Go 1.22+** (backend/core)

Install frontend deps once: `cd tests/frontend && npm install`
