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
| **mineru** | `mineru` | `LAZYRAG_OCR_SERVER_TYPE=mineru` and URL `http://mineru:8000` | MinerU PDF parsing (layout analysis; install variant/backend configurable) |
| **paddleocr** + **paddleocr-vlm-server** | `paddleocr` | `LAZYRAG_OCR_SERVER_TYPE=paddleocr` and URL `http://paddleocr:8080` | PaddleOCR-VL PDF parsing (GPU required) |
| **milvus** + **milvus-etcd** + **milvus-minio** | `milvus` | `LAZYRAG_MILVUS_URI=http://milvus:19530` | Vector store for embeddings |
| **attu** | `milvus-dashboard` | `LAZYRAG_ENABLE_MILVUS_DASHBOARD=1` and `LAZYRAG_MILVUS_URI=http://milvus:19530` | Milvus dashboard for collections, schema, and index troubleshooting |
| **opensearch** | `opensearch` | `LAZYRAG_OPENSEARCH_URI=https://opensearch:9200` | Segment store for document chunks |
| **opensearch-dashboards** | `opensearch-dashboard` | `LAZYRAG_ENABLE_OPENSEARCH_DASHBOARD=1` and `LAZYRAG_OPENSEARCH_URI=https://opensearch:9200` | OpenSearch dashboard for index, mapping, and query inspection |

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

## Runtime Model Config

- The default runtime config file is `algorithm/chat/runtime_models.yaml`. Set `LAZYRAG_USE_INNER_MODEL=true` to use the internal deployment config (`runtime_models.inner.yaml`) instead.
- Configure `llm`, `llm_instruct`, `reranker`, and `embed_1~embed_3` directly with `source/api_key/model/type/url`.
- Keep real secrets out of git. Prefer env placeholders such as `${LAZYLLM_SILICONFLOW_API_KEY}`.
- For local debugging with a temporary config file, set `LAZYRAG_MODEL_CONFIG_PATH=/app/tmp/your-config.yaml`; `docker-compose.yml` mounts the repository `tmp/` directory into `/app/tmp` inside the containers.
- If only `embed_1` is configured, indexing, ingestion, and retrieval run in single-embedding mode automatically. Enabling `embed_2/embed_3` keeps parsing and retrieval on the same `embed_key` set.

## Quick Start

For environment-variable setup and runnable startup examples, see:

- [`docs/quick_start.md`](docs/quick_start.md)

**Full stack (Milvus + OpenSearch deployed by default):**
```bash
make up
```

**Full stack with built-in store dashboards:**
```bash
make up LAZYRAG_ENABLE_STORE_DASHBOARDS=1
```

**Enable only the Milvus dashboard (Attu):**
```bash
make up LAZYRAG_ENABLE_MILVUS_DASHBOARD=1
```

**Enable only OpenSearch Dashboards:**
```bash
make up LAZYRAG_ENABLE_OPENSEARCH_DASHBOARD=1
```

**With external Milvus/OpenSearch** (no deployment of milvus/opensearch):
```bash
make up LAZYRAG_MILVUS_URI=http://your-milvus:19530 LAZYRAG_OPENSEARCH_URI=https://your-opensearch:9200
```

**With MinerU OCR:**
```bash
make up LAZYRAG_OCR_SERVER_TYPE=mineru
```

**With MinerU `all` install variant:**
```bash
make up LAZYRAG_OCR_SERVER_TYPE=mineru LAZYRAG_MINERU_PACKAGE_VARIANT=all LAZYRAG_MINERU_PREINSTALL_CPU_TORCH=0
```

**With MinerU backend override:**
```bash
make up LAZYRAG_OCR_SERVER_TYPE=mineru LAZYRAG_MINERU_BACKEND=hybrid-auto-engine
```

**With PaddleOCR (GPU):**
```bash
make up LAZYRAG_OCR_SERVER_TYPE=paddleocr
```

The Makefile auto-selects profiles based on env vars. You can also run `docker compose up --build` directly; optional services won't start unless you pass `--profile mineru`, `--profile paddleocr`, `--profile milvus`, `--profile opensearch`, `--profile milvus-dashboard`, or `--profile opensearch-dashboard`.

Built-in store dashboards are disabled by default. When enabled, they bind only to `127.0.0.1` and are started only if the corresponding built-in store is still in use:

- Attu (Milvus): http://127.0.0.1:3000
- OpenSearch Dashboards: http://127.0.0.1:5601
- OpenSearch Dashboards login: `admin` / `LAZYRAG_OPENSEARCH_PASSWORD`
- If `LAZYRAG_MILVUS_URI` or `LAZYRAG_OPENSEARCH_URI` points to an external service, the matching built-in dashboard is not deployed even when the flag is set.

MinerU configuration is split into two layers:

- Install variant: `LAZYRAG_MINERU_PACKAGE_VARIANT` (for example `pipeline` or `all`).
- Runtime backend: `LAZYRAG_MINERU_BACKEND` (for example `pipeline` or `hybrid-auto-engine`).
- Compatibility pin: `LAZYRAG_MINERU_NUMPY_VERSION` defaults to `1.26.4` so the MinerU image stays compatible with bundled `lazyllm/spacy`.

For local CPU development on macOS, the default combination is `LAZYRAG_MINERU_PACKAGE_VARIANT=pipeline` plus `LAZYRAG_MINERU_BACKEND=pipeline`.

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
| chat              | `LAZYRAG_DOCUMENT_SERVER_URL`, `LAZYRAG_MAX_CONCURRENCY` | Document API and concurrency    |

Override store endpoints when using external Milvus/OpenSearch; built-in services are deployed only when the URIs stay at `http://milvus:19530` and `https://opensearch:9200`.

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
