# LazyRAG

**[中文](README.CN.md)** | **English**

A full-stack application with Kong API Gateway, JWT/RBAC auth, Go core API, Python algorithm services (document parsing, RAG chat), and a simple web frontend.

## Architecture

- **Kong** (port 8000): API gateway with declarative config; routes `/api/auth`, `/api/chat`, and `/api` to backend services; RBAC plugin for protected routes.
- **Frontend** (port 8080): Static SPA (nginx) — login, token refresh, chat UI, calls Kong.
- **auth-service**: FastAPI auth — register, login, refresh, roles, permissions; bootstrap admin; used by Kong `rbac-auth` plugin.
- **core**: Go HTTP service — dataset, document, task, retrieval, etc. (stub handlers); behind Kong with RBAC.
- **Algorithm stack**:
  - **processor-server**: Document task queue server.
  - **processor-worker**: Document task execution worker.
  - **parsing**: Document service (lazyllm RAG) — vector/segment stores (Milvus+OpenSearch), PDF reader (built-in, MinerU, or PaddleOCR).
  - **chat**: RAG chat API (lazyllm) on port 8046; uses parsing service for documents.

- **PostgreSQL** (db): Used by auth-service and processor for app data and doc tasks.

## Service Dependencies (depends_on)

Dependency graph from `docker-compose.yml` (A → B means A waits for B to start):

```
db
├── auth-service
│   └── kong
│       └── frontend
├── core (also ← auth-service)
└── processor-server
    └── processor-worker (also ← db)
        └── parsing
            └── chat
```

| Service | Depends on |
|---------|------------|
| db | — |
| auth-service | db |
| kong | auth-service |
| frontend | kong |
| core | db, auth-service |
| processor-server | db |
| processor-worker | db, processor-server |
| parsing | processor-server, processor-worker |
| chat | parsing |

**Optional services** (profile-based):

| Service | Depends on |
|---------|------------|
| mineru | — |
| paddleocr-vlm-server | — |
| paddleocr | paddleocr-vlm-server |
| milvus-etcd, milvus-minio | — |
| milvus | milvus-etcd, milvus-minio |
| opensearch | — |

## Optional Services

| Service | Profile | When enabled | Purpose |
|---------|---------|--------------|---------|
| **mineru** | `mineru` | `LAZYRAG_OCR_SERVER_TYPE=mineru` and URL `http://mineru:8000` | MinerU PDF parsing (layout analysis) |
| **paddleocr** + **paddleocr-vlm-server** | `paddleocr` | `LAZYRAG_OCR_SERVER_TYPE=paddleocr` and URL `http://paddleocr:8080` | PaddleOCR-VL PDF parsing (GPU required) |
| **milvus** + **milvus-etcd** + **milvus-minio** | `milvus` | `LAZYRAG_MILVUS_URI` contains `milvus:19530` | Vector store for embeddings |
| **opensearch** | `opensearch` | `LAZYRAG_OPENSEARCH_URI` contains `opensearch:9200` | Segment store for document chunks |

**Store for parsing** (required when using Processor/Worker):

- **Milvus + OpenSearch** are always required. If `LAZYRAG_MILVUS_URI` / `LAZYRAG_OPENSEARCH_URI` point to built-in services (`milvus:19530`, `opensearch:9200`), they are deployed automatically. If you provide external URIs, no deployment is needed.

**OCR modes for parsing**:

- **none** (default): Built-in PDFReader.
- **mineru**: MinerU service (profile `mineru`).
- **paddleocr**: PaddleOCR-VL service (profile `paddleocr`, GPU required).

## Request Flow (Verification Chain)

User requests from frontend to backend pass through the following verification steps:

```
Frontend
   │
   ├─► 1. auth-service (obtain JWT)
   │      Login / register → auth-service returns JWT → frontend stores token
   │
   └─► 2. Kong (RBAC)
          API request with JWT → Kong rbac-auth plugin → auth-service /api/auth/authorize
          → validates JWT and route permission → forwards if allowed
          │
          ▼
       3. Backend (core) — ACL + handler
          Core receives request → ACL check (resource-level, e.g. kb_id, dataset_id)
          → executes handler or proxies to algorithm
          │
          ▼
       4. Algorithm
          Core proxies to Python services (chat, parsing, etc.) for RAG / document processing
```

| Step | Component | Role |
|------|-----------|------|
| 1 | auth-service | Issues JWT on login/register; frontend stores it |
| 2 | Kong | RBAC: validates JWT and route permission via auth-service authorize |
| 3 | core (backend) | ACL: resource-level permission (kb, dataset); handler execution |
| 4 | algorithm | RAG chat, document parsing, task processing |

## Prerequisites

- Docker and Docker Compose
- (Optional) Go 1.22 for `backend/core`, Python 3.11+ and flake8 for local dev/lint

## Quick Start

**Full stack (Milvus + OpenSearch deployed by default):**
```bash
make up
```

**With external Milvus/OpenSearch** (no deployment of milvus/opensearch):
```bash
make up LAZYRAG_MILVUS_URI=http://your-milvus:19530 LAZYRAG_OPENSEARCH_URI=https://your-opensearch:9200
```

**With MinerU OCR:**
```bash
make up LAZYRAG_OCR_SERVER_TYPE=mineru
```

**With PaddleOCR (GPU):**
```bash
make up LAZYRAG_OCR_SERVER_TYPE=paddleocr
```

The Makefile auto-selects profiles based on env vars. You can also run `docker compose up --build` directly; optional services won't start unless you pass `--profile mineru`, `--profile paddleocr`, `--profile milvus`, `--profile opensearch`.

- Frontend: http://localhost:8080  
- Kong (API): http://localhost:8000  
- Default admin: `admin` / `admin` (from auth-service bootstrap)

## Swagger / API docs

**Unified docs**: http://localhost:8080/docs.html — tabbed view of all service Swagger UIs. The frontend proxies to each service via Docker network (e.g. `auth-service:8000`), so no extra port mappings are needed.

## Project Layout

```
LazyRAG/
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
│   ├── common/                # Shared utilities (e.g. DB URL parsing)
│   ├── parsing/               # Document server (lazyllm, MinerU, Milvus, OpenSearch)
│   ├── processor/             # server + worker for doc tasks
│   ├── parsing/mineru.py      # MinerU PDF server
│   └── requirements.txt       # lazyllm[rag-advanced]
├── api/                       # OpenAPI specs (centralized)
│   ├── backend/core/           # core service OpenAPI
│   ├── backend/auth-service/   # auth-service OpenAPI
│   └── algorithm/             # algorithm services OpenAPI
├── kong/plugins/rbac-auth/     # Kong RBAC plugin (auth_service_url)
├── scripts/                   # e.g. gen_openapi_rag.sh
└── tests/
    ├── backend/               # Backend tests
    └── algorithm/             # Algorithm tests
```

- **Go module**: `backend/core` uses `module lazyrag/core` by design; the short module path keeps imports concise.
- **OpenAPI**: Specs live in `api/` and mirror service layout; keep them in sync when adding routes.

## Environment (notable)

| Service / scope   | Variable                       | Example / note                          |
|-------------------|--------------------------------|-----------------------------------------|
| auth-service      | `DATABASE_URL`                 | PostgreSQL connection                    |
| auth-service      | `JWT_SECRET`, `JWT_TTL_MINUTES`, `JWT_REFRESH_TTL_DAYS` | Token config      |
| auth-service      | `BOOTSTRAP_ADMIN_*`            | Initial admin user                      |
| processor-*       | `DOC_TASK_DATABASE_URL`        | Same DB for doc tasks                   |
| parsing           | `LAZYRAG_OCR_SERVER_TYPE`      | `none` \| `mineru` \| `paddleocr`       |
| parsing           | `LAZYRAG_MILVUS_URI`, `LAZYRAG_OPENSEARCH_URI`, `LAZYRAG_OPENSEARCH_USER`, `LAZYRAG_OPENSEARCH_PASSWORD` | Vector/segment stores (required) |
| opensearch (profile) | `LAZYRAG_OPENSEARCH_PASSWORD` | Override for production |
| milvus-minio (profile) | `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY` | Override for production |
| chat              | `DOCUMENT_SERVER_URL`, `MAX_CONCURRENCY` | Document API and concurrency    |

Override store endpoints when using external Milvus/OpenSearch; if URIs do not contain `milvus:19530` or `opensearch:9200`, those services are not deployed.

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
