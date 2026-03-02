# Hello Kong

**[中文](README.CN.md)** | **English**

A full-stack application with Kong API Gateway, JWT/RBAC auth, Go core API, Python algorithm services (document parsing, RAG chat), and a simple web frontend.

## Architecture

- **Kong** (port 8000): API gateway with declarative config; routes `/api/auth`, `/api/chat`, and `/api` to backend services; RBAC plugin for protected routes.
- **Frontend** (port 8080): Static SPA (nginx) — login, token refresh, chat UI, calls Kong.
- **auth-service**: FastAPI auth — register, login, refresh, roles, permissions; bootstrap admin; used by Kong `rbac-auth` plugin.
- **core**: Go HTTP service — dataset, document, task, retrieval, etc. (stub handlers); behind Kong with RBAC.
- **Algorithm stack**:
  - **mineru**: PDF parsing (MinerU).
  - **processor-server** / **processor-worker**: Document task queue and processing.
  - **parsing**: Document service (lazyllm RAG) — vector store (Milvus), segment store (OpenSearch), MinerU reader.
  - **chat**: RAG chat API (lazyllm) on port 8046; uses parsing service for documents.

- **PostgreSQL** (db): Used by auth-service and processor for app data and doc tasks.

## Prerequisites

- Docker and Docker Compose
- (Optional) Go 1.22 for `backend/core`, Python 3.11+ and flake8 for local dev/lint

## Quick Start

```bash
docker compose up --build
```

- Frontend: http://localhost:8080  
- Kong (API): http://localhost:8000  
- Default admin: `admin` / `admin` (from auth-service bootstrap)

## Project Layout

```
hello-kong/
├── kong.yml                    # Kong declarative config (routes, rbac-auth)
├── docker-compose.yml          # All services
├── Makefile                    # Lint: flake8 (algorithm, backend), gofmt (backend/core)
├── backend/
│   ├── auth-service/          # FastAPI auth, JWT, RBAC, bootstrap
│   ├── core/                  # Go API (dataset, document, task, retrieval, …)
│   └── scripts/               # e.g. extract_api_permissions for auth
├── frontend/                  # nginx + index.html SPA
├── algorithm/
│   ├── chat/                  # RAG chat (lazyllm)
│   ├── parsing/                # Document server (lazyllm, MinerU, Milvus, OpenSearch)
│   ├── processor/             # server + worker for doc tasks
│   ├── parsing/mineru.py       # MinerU PDF server
│   └── requirements.txt       # lazyllm[rag-advanced]
└── kong/plugins/rbac-auth/    # Kong RBAC plugin (auth_service_url)
```

## Environment (notable)

| Service / scope   | Variable                  | Example / note                          |
|-------------------|---------------------------|-----------------------------------------|
| auth-service      | `DATABASE_URL`            | PostgreSQL connection                   |
| auth-service      | `JWT_SECRET`, `JWT_TTL_MINUTES`, `JWT_REFRESH_TTL_DAYS` | Token config     |
| auth-service      | `BOOTSTRAP_ADMIN_*`       | Initial admin user                      |
| processor-*       | `DOC_TASK_DATABASE_URL`   | Same DB for doc tasks                   |
| parsing           | `MILVUS_URI`, `OPENSEARCH_URI`, `OPENSEARCH_USER`, `OPENSEARCH_PASSWORD` | Stores |
| chat              | `DOCUMENT_SERVER_URL`, `MAX_CONCURRENCY` | Document API and concurrency   |

Override store endpoints when not using defaults, e.g. in `docker-compose.yml` or env files.

## Lint

```bash
make lint              # Python (algorithm, backend) + Go (backend/core)
make lint-only-diff    # Lint only changed files (Python + Go)
```

Python uses flake8 (excluding submodule `algorithm/lazyllm` per `.flake8`); Go uses `gofmt`.

## API Summary

- **Kong**  
  - `POST /api/auth/*` → auth-service (login, register, refresh, roles, authorize).  
  - `POST /api/chat`, `POST /api/chat/stream` → chat (no Kong RBAC; frontend → Kong → chat).  
  - `/api/*` (other) → core (with Kong RBAC).

- **auth-service** (via Kong): login, register, refresh, roles, permissions, user-role assignment, authorize (method + path).

## License

See repository for license information.
