# evo POC service

Independent FastAPI service that wraps the evo diagnosis pipeline and
opencode-driven code apply. It runs in its own container, talks to the
`chat` service over HTTP for LLM/embedding calls, and keeps all state in
SQLite + filesystem under `./data/evo`.

## Layout

```
./data/evo/
  state.db                       # SQLite state machine
  opencode/auth.json             # opencode credentials (admin API)
  runs/<run_id>/
    telemetry.jsonl              # SSE tail source
    handles.jsonl
    world_model.json
    raw/                         # schema-repair raw responses
    steps/<step>.pickle          # step checkpoints (for resume)
  applies/<apply_id>/
    rounds/round_NNN/
      input/prompt.txt
      opencode/{stdout,stderr,events.jsonl,text_summary.md}
      tests/{test.log,traceback.md}
  reports/<report_id>.{json,md}  # never deleted by any action
  diffs/<apply_id>/
    index.json                   # self-describing diff map
    <basename>_<sha>.diff
  git/
    chat.git/                    # bare repo of algorithm/chat snapshot
    worktrees/apply_<id>/        # per-apply worktree
```

## Action semantics

| Action | run                      | apply                                                     |
|--------|--------------------------|-----------------------------------------------------------|
| execute | enqueue + start          | enqueue + start (default report = latest succeeded run)   |
| stop    | flag stop, ack at boundary -> paused | same                                          |
| continue | restart from checkpoint | restart, reuse worktree commits                           |
| cancel  | terminal; delete run dir | terminal; SIGTERM procs + delete worktree+branch+diffs+logs |
| accept  | n/a                      | terminal; keep everything (worktree, diffs, logs)         |
| reject  | n/a                      | terminal; delete worktree+branch+diffs, keep round logs   |

There is no `retry`; "再来一次" is `cancel` + `execute` (per `design.md`).
A flow allows at most one non-terminal task at a time; for apply,
`succeeded` blocks new applies until accept/reject.

## State machine

```
empty -> running -> stopping -> paused -> running -> succeeded
                  -> failed_transient -> running
                  -> failed_permanent -> cancelled
                  -> cancelled
running -> succeeded (run terminal)
running -> succeeded -> accepted | rejected (apply only)
```

Permanent failures (`OPENCODE_BIN_MISSING`, `OPENCODE_AUTH_MISSING`,
`REPORT_INVALID`, `CODE_MAP_EMPTY`, `STATE_DRIFT`) cannot continue;
client should `cancel` then `execute` after fixing config.

## API

Mounted under `/v1/evo` (Kong route `/api/evo` strips this in production).

**Interactive docs**: once the service is running, browse
- Swagger UI: `http://localhost:8047/docs`
- ReDoc:      `http://localhost:8047/redoc`
- Raw OpenAPI JSON: `http://localhost:8047/openapi.json`

All routes are tagged (`runs` / `applies` / `reports` / `admin` / `health`)
and have request/response models so that Swagger renders typed schemas.

```
# task control
POST   /v1/evo/runs                          execute (no body)
POST   /v1/evo/applies                       execute (body: {report_id?})
GET    /v1/evo/runs                          list recent
GET    /v1/evo/runs/{id}
GET    /v1/evo/applies
GET    /v1/evo/applies/{id}                  includes rounds[]

# actions
POST   /v1/evo/runs/{id}/{stop|continue|cancel}
POST   /v1/evo/applies/{id}/{stop|continue|cancel|accept|reject}

# realtime
GET    /v1/evo/runs/{id}/telemetry           SSE
GET    /v1/evo/runs/{id}/world               world_model snapshot
GET    /v1/evo/runs/{id}/handles?since=N
GET    /v1/evo/applies/{id}/telemetry        SSE

# artifacts
GET    /v1/evo/runs/{id}/report              latest report metadata for run
GET    /v1/evo/reports/{rid}/content?fmt=json|md
GET    /v1/evo/applies/{id}/diff-map         {apply_id, base_commit, files[]}
GET    /v1/evo/diffs/{apply_id}/{name}.diff

# admin
GET    /v1/evo/admin/opencode/status
PUT    /v1/evo/admin/opencode/config         body: {provider, api_key, model?}
DELETE /v1/evo/admin/opencode/config
```

`Idempotency-Key` header on `POST /runs` and `POST /applies` returns
the cached response within 30 seconds.

## Frontend button visibility

| status                 | run buttons       | apply buttons             |
|------------------------|-------------------|---------------------------|
| empty                  | execute           | execute                   |
| running                | stop, cancel      | stop, cancel              |
| stopping               | (loading)         | (loading)                 |
| paused                 | continue, cancel  | continue, cancel          |
| failed_transient       | continue, cancel  | continue, cancel          |
| failed_permanent       | cancel            | cancel                    |
| succeeded              | view              | accept, reject            |
| accepted               | -                 | view (read-only)          |
| rejected / cancelled   | execute (new)     | execute (new)             |

## Local development

```bash
# 1. install deps
python3 -m pip install --user -r evo/requirements.txt

# 2. ensure chat is reachable (defaults to http://chat:8046)
export EVO_CHAT_BASE_URL=http://localhost:8046
export EVO_CHAT_INTERNAL_TOKEN=dev-internal-service-token

# 3. start the service (factory mode, picks up config from env)
python3 -m uvicorn evo.service.api:get_app --factory --host 0.0.0.0 --port 8047

# 4. seed opencode auth (one-time, then API takes over)
curl -X PUT http://localhost:8047/v1/evo/admin/opencode/config \
  -H 'Content-Type: application/json' \
  -d '{"provider":"anthropic","api_key":"YOUR_KEY"}'
```

## Container deployment

```bash
docker compose build evo-api
docker compose up -d evo-api
docker compose logs -f evo-api

# end-to-end smoke (after chat is up):
curl http://localhost:8047/healthz
curl -X PUT http://localhost:8047/v1/evo/admin/opencode/config \
  -H 'Content-Type: application/json' \
  -d "{\"provider\":\"anthropic\",\"api_key\":\"$EVO_OPENCODE_ANTHROPIC_KEY\"}"
RUN_ID=$(curl -sX POST http://localhost:8047/v1/evo/runs | jq -r .id)
curl -N http://localhost:8047/v1/evo/runs/$RUN_ID/telemetry  # SSE
curl http://localhost:8047/v1/evo/runs/$RUN_ID/report
APPLY_ID=$(curl -sX POST http://localhost:8047/v1/evo/applies | jq -r .id)
curl http://localhost:8047/v1/evo/applies/$APPLY_ID/diff-map
curl -X POST http://localhost:8047/v1/evo/applies/$APPLY_ID/accept
```

## Configuration

All knobs are environment variables, picked up by `load_config()`:

| variable                       | default                                  |
|--------------------------------|------------------------------------------|
| `EVO_BASE_DIR`                 | `<repo>/data/evo`                        |
| `EVO_DATA_DIR`                 | `<evo>/data`                             |
| `EVO_CHAT_BASE_URL`            | `http://chat:8046`                       |
| `EVO_CHAT_INTERNAL_TOKEN`      | (empty)                                  |
| `EVO_CHAT_LLM_ROLE`            | `evo_llm`                                |
| `EVO_CHAT_EMBED_ROLE`          | `evo_embed`                              |
| `EVO_CHAT_SOURCE`              | `<repo>/algorithm/chat`                  |
| `EVO_CODE_MAP`                 | (empty; required for apply)              |
| `OPENCODE_DATA_DIR`            | `/var/lib/lazyrag/evo/opencode` (container) |
| `EVO_OPENCODE_ANTHROPIC_KEY`   | first-boot bootstrap; API overrides      |
| `EVO_OPENCODE_AUTH_JSON`       | full auth.json blob (alternative)        |

The frontend has zero configuration UI; all of these are server-side only.

## Operations

- Reset a stuck worktree: `git -C ./data/evo/git/chat.git worktree prune`
- Reset opencode auth: `DELETE /v1/evo/admin/opencode/config` then `PUT` again.
- Wipe everything: `rm -rf ./data/evo` (containers will recreate the layout).
- Refresh chat baseline: delete `./data/evo/git/chat.git`; next apply re-init.
