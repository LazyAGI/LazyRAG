# scan-control-plane

`scan-control-plane` is the control-plane service for local directory sources.

It provides:

- Source CRUD and enable/disable APIs for frontend.
- Agent register/heartbeat/pull/event ingestion APIs for file-watcher.
- Agent command ACK API (`/api/v1/agents/commands/ack`) for reliable delivery.
- Frontend helper APIs to validate paths and fetch directory tree via selected agent.
- Idle-window scheduler that turns due documents into parse tasks.
- In-memory event merger + batch document upsert to reduce DB hot writes.
- Built-in parse task worker with pre/post commit-gate checks and retry.
- Stage-file command ACK wait + timeout requeue for reliable delivery.
- Source-level `dataset_id` binding and core-task submission flow.
- Periodic metrics snapshot logging for queue/backlog/offline visibility.

## Run

```bash
cd /Users/sunjinghua.vendor/sunjh/LazyRAG-Scan/LazyRAG/backend/scan-control-plane
go run ./cmd/main.go -config configs/control-plane.yaml
```

## Core APIs

### Source APIs (frontend)

- `POST /api/v1/sources`
- `GET /api/v1/sources?tenant_id=...`
- `GET /api/v1/sources/{id}`
- `PUT /api/v1/sources/{id}`
- `POST /api/v1/sources/{id}/enable`
- `POST /api/v1/sources/{id}/disable`
- `POST /api/v1/sources/{id}/tasks/generate`
- `POST /api/v1/sources/{id}/watch/enable`
- `POST /api/v1/sources/{id}/watch/disable`
- `POST /api/v1/sources/{id}/tasks/expedite`

### Agent APIs (file-watcher)

- `POST /api/v1/agents/register`
- `POST /api/v1/agents/heartbeat`
- `POST /api/v1/agents/pull`
- `POST /api/v1/agents/commands/ack`
- `POST /api/v1/agents/snapshots/report`
- `POST /api/v1/agents/events`
- `POST /api/v1/agents/scan-results`
- `GET /api/v1/agents`
- `GET /api/v1/agents/{id}`

### Frontend helper APIs (path config / folder tree)

- `POST /api/v1/agents/fs/validate`
- `POST /api/v1/agents/fs/tree`

Example: validate path

```bash
curl -s -X POST http://127.0.0.1:18080/api/v1/agents/fs/validate \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id":"file-watcher-local-001",
    "path":"/tmp/test-watch"
  }'
```

Example: fetch directory tree (directories only)

```bash
curl -s -X POST http://127.0.0.1:18080/api/v1/agents/fs/tree \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id":"file-watcher-local-001",
    "path":"/tmp/test-watch",
    "max_depth":2,
    "include_files":false
  }'
```
