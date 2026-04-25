# evo POC service

Independent FastAPI service for the evo diagnosis loop:

```text
dataset_gen -> eval -> run -> apply -> accept -> merge -> deploy -> abtest
```

Both REST APIs and natural-language threads execute through `OpsExecutor`.
State is stored under `./data/evo`.

## Data Layout

```text
./data/evo/
  state/
    tasks/<task_id>.json              # task state machine records
    apply_rounds/<apply_id>/          # apply round metadata
    intents/                          # pending/confirmed thread intents
    threads/<thread_id>/              # thread messages, events, artifacts
    chats/                            # local candidate chat process logs
  runs/<run_id>/
    telemetry.jsonl                   # run event stream source
    handles.jsonl                     # tool-call result handles
    world_model.json                  # current diagnosis hypotheses
    raw/                              # raw agent responses
    steps/<step>.pickle               # pipeline checkpoints
  applies/<apply_id>/                 # apply execution logs
  reports/<report_id>.{json,md}       # diagnosis reports
  diffs/<apply_id>/                   # generated diffs
  datasets/<dataset_id>/eval_data.json
  deploys/<deploy_id>/deployment.json
  git/chat.git                        # bare repo snapshot for apply/merge
  git/worktrees/apply_<apply_id>/     # per-apply worktree
  opencode/auth.json                  # opencode credentials
```

`StorageConfig.ensure()` also creates some empty flow directories (`run`,
`apply`, `eval`, `merge`, `deploy`, `dataset_gen`, `abtest`) as event/artifact
roots. Empty directories are safe to delete, but they will be recreated on
service startup.

## Start Commands

Run from the repository root (`LazyRAG/`):

```bash
# Install dependencies if needed.
python3 -m pip install --user -r LazyRAG/evo/requirements.txt

# Configure model access.
export LAZYRAG_USE_INNER_MODEL=true
export LAZYRAG_MAAS_API_KEY=...

# Optional but usually needed for apply.
export EVO_CODE_MAP=/abs/path/to/code_map.json
export EVO_CHAT_SOURCE=/abs/path/to/algorithm/chat

# Start API service.
PYTHONPATH=LazyRAG python3 -m uvicorn evo.service.api:get_app \
  --factory --host 0.0.0.0 --port 8047
```

Local docs:

```bash
open http://localhost:8047/docs
open http://localhost:8047/redoc
curl http://localhost:8047/openapi.json
```

Container commands:

```bash
docker compose build evo-api
docker compose up -d evo-api
docker compose logs -f evo-api
```

CLI commands:

```bash
PYTHONPATH=LazyRAG python3 -m evo.main pipeline --code-map /path/to/code_map.json
PYTHONPATH=LazyRAG python3 -m evo.main --base-dir ./LazyRAG/data/evo thread auto --timeout-s 3600
PYTHONPATH=LazyRAG python3 -m evo.main thread chat -m "分析刚才的评测报告"
PYTHONPATH=LazyRAG python3 -m evo.main thread decide --badcase-limit 50
```

## API Conventions

Set a base URL for examples:

```bash
BASE=http://localhost:8047
JSON='Content-Type: application/json'
```

Create endpoints support `Idempotency-Key`:

```bash
curl -sX POST "$BASE/v1/evo/runs" \
  -H "$JSON" \
  -H "Idempotency-Key: demo-run-001" \
  -d '{}'
```

Create/action responses use this shape:

```json
{
  "op": "run.start",
  "task_id": "run_...",
  "status": "submitted",
  "error": null,
  "data": null
}
```

Health checks:

```bash
curl -s "$BASE/healthz"
curl -s "$BASE/livez"
curl -s "$BASE/readyz"
```

## Flow APIs

The seven task flows are:

- `runs`
- `applies`
- `datasets`
- `evals`
- `merges`
- `deploys`
- `abtests`

Common endpoints:

```text
POST /v1/evo/<flow>             create task
GET  /v1/evo/<flow>?limit=50    list recent tasks
GET  /v1/evo/<flow>/<id>        get task detail
GET  /v1/evo/<flow>/<id>/events stream task events as SSE
POST /v1/evo/<flow>/<id>/cancel cancel task
```

Supported stop/continue:

```text
POST /v1/evo/runs/<id>/stop
POST /v1/evo/runs/<id>/continue
POST /v1/evo/applies/<id>/stop
POST /v1/evo/applies/<id>/continue
POST /v1/evo/deploys/<id>/continue
POST /v1/evo/abtests/<id>/stop
POST /v1/evo/abtests/<id>/continue
```

### Runs

Create payload:

```json
{
  "thread_id": "thr-optional",
  "eval_id": "eval_optional",
  "badcase_limit": 20,
  "score_field": "answer_correctness"
}
```

Commands:

```bash
RUN_ID=$(curl -sX POST "$BASE/v1/evo/runs" \
  -H "$JSON" \
  -d '{"badcase_limit":20,"score_field":"answer_correctness"}' | jq -r .task_id)

curl -s "$BASE/v1/evo/runs?limit=20" | jq .
curl -s "$BASE/v1/evo/runs/$RUN_ID" | jq .
curl -N "$BASE/v1/evo/runs/$RUN_ID/events"
curl -s "$BASE/v1/evo/runs/$RUN_ID/handles?since=0" | jq .
curl -sX POST "$BASE/v1/evo/runs/$RUN_ID/stop" | jq .
curl -sX POST "$BASE/v1/evo/runs/$RUN_ID/continue" | jq .
curl -sX POST "$BASE/v1/evo/runs/$RUN_ID/cancel" | jq .
```

### Applies

Apply runs opencode multi-round code modification in an isolated Git worktree.
Each round: code modification -> unit test.  After all tests pass, diff preview
is generated.  Stop is a graceful pause; cancel/reject cleans worktree & diffs;
continue resumes from the last checkpoint.

Create payload:

```json
{
  "thread_id": "thr-optional",
  "report_id": "report_optional"
}
```

If `report_id` is omitted, the manager resolves the latest available report
for the thread, then globally.

Commands:

```bash
APPLY_ID=$(curl -sX POST "$BASE/v1/evo/applies" \
  -H "$JSON" \
  -d '{"report_id":"REPORT_ID"}' | jq -r .task_id)

curl -s "$BASE/v1/evo/applies?limit=20" | jq .
curl -s "$BASE/v1/evo/applies/$APPLY_ID" | jq .
curl -N "$BASE/v1/evo/applies/$APPLY_ID/events"
curl -sX POST "$BASE/v1/evo/applies/$APPLY_ID/stop" | jq .
curl -sX POST "$BASE/v1/evo/applies/$APPLY_ID/continue" | jq .
curl -sX POST "$BASE/v1/evo/applies/$APPLY_ID/cancel" | jq .
curl -sX POST "$BASE/v1/evo/applies/$APPLY_ID/reject" | jq .
```

`apply.stop` is a graceful pause (checkpoint preserved); `apply.cancel`
discards worktree + diffs + logs; `apply.reject` discards diffs while keeping
logs.  `apply.continue` resumes from the last checkpoint without rebuilding
the worktree.

Accept modes (`auto_next` accepts only `none`, `merge`, `merge_deploy`):

```bash
# Accept only.
curl -sX POST "$BASE/v1/evo/applies/$APPLY_ID/accept?auto_next=none" | jq .

# Accept and submit merge.
curl -sX POST "$BASE/v1/evo/applies/$APPLY_ID/accept?auto_next=merge" | jq .

# Accept, submit merge, and auto-submit deploy after merge succeeds.
curl -sX POST "$BASE/v1/evo/applies/$APPLY_ID/accept?auto_next=merge_deploy" | jq .
```

### Datasets

Create payload:

```json
{
  "thread_id": "thr-optional",
  "kb_id": "KB_ID",
  "algo_id": "general_algo",
  "eval_name": "demo_eval"
}
```

Commands:

```bash
DATASET_TASK_ID=$(curl -sX POST "$BASE/v1/evo/datasets" \
  -H "$JSON" \
  -d '{"kb_id":"KB_ID","algo_id":"general_algo","eval_name":"demo_eval"}' | jq -r .task_id)

curl -s "$BASE/v1/evo/datasets?limit=20" | jq .
curl -s "$BASE/v1/evo/datasets/$DATASET_TASK_ID" | jq .
curl -N "$BASE/v1/evo/datasets/$DATASET_TASK_ID/events"
curl -sX POST "$BASE/v1/evo/datasets/$DATASET_TASK_ID/cancel" | jq .
```

### Evals

Create payload:

```json
{
  "thread_id": "thr-required",
  "dataset_id": "demo_eval",
  "eval_id": null,
  "target_chat_url": "http://localhost:8000/chat",
  "options": {
    "max_workers": 10,
    "dataset_name": ""
  }
}
```

Dispatch (automatic based on the payload):

- `dataset_id` present → `eval.run` — asynchronously runs a new eval on the
  given dataset and fetches all traces.
- only `eval_id` present → `eval.fetch` — fetches an existing eval report
  and its traces from the upstream evaluation system.

Commands:

```bash
# Run a new eval on a dataset.
EVAL_TASK_ID=$(curl -sX POST "$BASE/v1/evo/evals" \
  -H "$JSON" \
  -d '{"thread_id":"THREAD_ID","dataset_id":"demo_eval","target_chat_url":"http://localhost:8000/chat","options":{"max_workers":10}}' | jq -r .task_id)

# Fetch an existing eval report.
curl -sX POST "$BASE/v1/evo/evals" \
  -H "$JSON" \
  -d '{"thread_id":"THREAD_ID","eval_id":"EVAL_ID"}' | jq .

curl -s "$BASE/v1/evo/evals?limit=20" | jq .
curl -s "$BASE/v1/evo/evals/$EVAL_TASK_ID" | jq .
curl -N "$BASE/v1/evo/evals/$EVAL_TASK_ID/events"
curl -sX POST "$BASE/v1/evo/evals/$EVAL_TASK_ID/cancel" | jq .
```

### Merges

Merge is a one-shot Git operation: `failed_permanent` on failure, no retry.

Create payload:

```json
{
  "thread_id": "thr-optional",
  "apply_id": "apply_...",
  "strategy": "merge-commit",
  "auto_deploy": false
}
```

`strategy` can be `merge-commit` (default), `squash`, or `fast-forward`.

Commands:

```bash
MERGE_ID=$(curl -sX POST "$BASE/v1/evo/merges" \
  -H "$JSON" \
  -d '{"apply_id":"APPLY_ID","strategy":"merge-commit"}' | jq -r .task_id)

curl -s "$BASE/v1/evo/merges?limit=20" | jq .
curl -s "$BASE/v1/evo/merges/$MERGE_ID" | jq .
curl -N "$BASE/v1/evo/merges/$MERGE_ID/events"
curl -sX POST "$BASE/v1/evo/merges/$MERGE_ID/cancel" | jq .
```

### Deploys

Deploy checks out the merge commit from `git/chat.git` into
`data/evo/deploys/<deploy_id>/source`, launches a production chat service,
registers it in ChatRegistry, and writes `deployment.json`.  The default role
is `production` and the old production chat is preserved.

Failure is transient, allowing `deploy.continue` for retry.

Create payload:

```json
{
  "thread_id": "thr-optional",
  "merge_id": "merge_...",
  "adapter": "local",
  "version": "latest",
  "role": "production",
  "keep_old": true
}
```

Commands:

```bash
DEPLOY_ID=$(curl -sX POST "$BASE/v1/evo/deploys" \
  -H "$JSON" \
  -d '{"merge_id":"MERGE_ID","adapter":"local","version":"latest"}' | jq -r .task_id)

curl -s "$BASE/v1/evo/deploys?limit=20" | jq .
curl -s "$BASE/v1/evo/deploys/$DEPLOY_ID" | jq .
curl -N "$BASE/v1/evo/deploys/$DEPLOY_ID/events"
curl -sX POST "$BASE/v1/evo/deploys/$DEPLOY_ID/cancel" | jq .
curl -sX POST "$BASE/v1/evo/deploys/$DEPLOY_ID/continue" | jq .
```

### ABTests

Create payload:

```json
{
  "thread_id": "thr-required",
  "apply_id": "apply_...",
  "baseline_eval_id": "eval_baseline",
  "dataset_id": "demo_eval",
  "apply_worktree": null,
  "target_chat_url": null,
  "eval_options": {
    "max_workers": 10,
    "dataset_name": ""
  },
  "policy": {
    "primary_metric": "answer_correctness",
    "eps": 0.01,
    "p_value": 0.05,
    "guard_metrics": ["doc_recall", "context_recall"],
    "guard_eps": 0.02
  }
}
```

Commands:

```bash
ABTEST_ID=$(curl -sX POST "$BASE/v1/evo/abtests" \
  -H "$JSON" \
  -d '{"thread_id":"THREAD_ID","apply_id":"APPLY_ID","baseline_eval_id":"BASELINE_EVAL_ID","dataset_id":"demo_eval"}' | jq -r .task_id)

curl -s "$BASE/v1/evo/abtests?limit=20" | jq .
curl -s "$BASE/v1/evo/abtests/$ABTEST_ID" | jq .
curl -N "$BASE/v1/evo/abtests/$ABTEST_ID/events"
curl -sX POST "$BASE/v1/evo/abtests/$ABTEST_ID/stop" | jq .
curl -sX POST "$BASE/v1/evo/abtests/$ABTEST_ID/continue" | jq .
curl -sX POST "$BASE/v1/evo/abtests/$ABTEST_ID/cancel" | jq .
```

## Artifact APIs

```bash
# Report file. fmt can be json or md.
curl -OJ "$BASE/v1/evo/reports/REPORT_ID/content?fmt=json"
curl -OJ "$BASE/v1/evo/reports/REPORT_ID/content?fmt=md"

# Diff file under data/evo/diffs/<apply_id>/.
curl -OJ "$BASE/v1/evo/diffs/$APPLY_ID/NAME.diff"

# Generic per-flow artifact under data/evo/<flow>/<task_id>/.
curl -OJ "$BASE/v1/evo/runs/$RUN_ID/artifacts/world_model.json"
curl -OJ "$BASE/v1/evo/evals/$EVAL_TASK_ID/artifacts/trace.bundle.json"
```

## Thread APIs

Natural-language threads use a two-phase flow:

```text
POST message -> planner draft intent -> POST confirm -> materialize ops -> execute
```

Commands:

```bash
# Create/list/get thread.
THREAD_ID=$(curl -sX POST "$BASE/v1/evo/threads" \
  -H "$JSON" \
  -d '{"title":"e2e","mode":"interactive"}' | jq -r .id)

curl -s "$BASE/v1/evo/threads" | jq .
curl -s "$BASE/v1/evo/threads/$THREAD_ID" | jq .

# Send natural-language message.
INTENT_ID=$(curl -sX POST "$BASE/v1/evo/threads/$THREAD_ID/messages" \
  -H "$JSON" \
  -d '{"content":"从知识库 KB_ID 生成评测集，名字叫 demo_eval"}' | jq -r .intent_id)

# Inspect pending intents and events.
curl -s "$BASE/v1/evo/threads/$THREAD_ID/intents" | jq .
curl -N "$BASE/v1/evo/threads/$THREAD_ID/events?since=0"

# Confirm intent.
curl -sX POST "$BASE/v1/evo/threads/$THREAD_ID/intents/$INTENT_ID:confirm" \
  -H "$JSON" \
  -d '{}' | jq .

# Confirm with explicit user_edit ops.
curl -sX POST "$BASE/v1/evo/threads/$THREAD_ID/intents/$INTENT_ID:confirm" \
  -H "$JSON" \
  -d '{"user_edit":{"ops":[{"op":"dataset_gen.start","args":{"kb_id":"KB_ID","eval_name":"demo_eval"}}]}}' | jq .

# Cancel pending intent.
curl -sX POST "$BASE/v1/evo/threads/$THREAD_ID/intents/$INTENT_ID:cancel" | jq .

# Show apply commits attached to a thread.
curl -s "$BASE/v1/evo/threads/$THREAD_ID/apply-commits" | jq .
```

Useful natural-language prompts:

```text
从知识库 KB_ID 生成评测集，名字叫 demo_eval
用 demo_eval 对当前 chat 评测并生成报告
分析刚才的评测报告
根据分析报告修改代码
接受修改并合并
部署刚才的 merge 结果
用 demo_eval 做 ABTest 比较修改效果
```

## Admin APIs

Opencode auth:

```bash
curl -s "$BASE/v1/evo/admin/opencode/status" | jq .

curl -sX PUT "$BASE/v1/evo/admin/opencode/config" \
  -H "$JSON" \
  -d '{"provider":"anthropic","api_key":"YOUR_KEY","model":"claude-3-5-sonnet-latest"}' | jq .

curl -sX DELETE "$BASE/v1/evo/admin/opencode/config" | jq .
```

Bulk stop/cancel:

```bash
# Thread scope requires thread_id.
curl -sX POST "$BASE/v1/evo/admin/runs:cancelAll?scope=thread&thread_id=$THREAD_ID" | jq .
curl -sX POST "$BASE/v1/evo/admin/applies:stopAll?scope=thread&thread_id=$THREAD_ID" | jq .

# Global scope requires EVO_ADMIN_TOKEN.
curl -sX POST "$BASE/v1/evo/admin/runs:cancelAll?scope=global" \
  -H "Authorization: Bearer $EVO_ADMIN_TOKEN" | jq .
curl -sX POST "$BASE/v1/evo/admin/abtests:stopAll?scope=global" \
  -H "Authorization: Bearer $EVO_ADMIN_TOKEN" | jq .
```

Admin flow path names use store flow names plus `s`: `runs`, `applies`,
`evals`, `abtests`, `merges`, `deploys`, and `dataset_gens`.

## End-to-End REST Example

```bash
BASE=http://localhost:8047
JSON='Content-Type: application/json'

THREAD_ID=$(curl -sX POST "$BASE/v1/evo/threads" \
  -H "$JSON" -d '{"title":"e2e"}' | jq -r .id)

DATASET_TASK_ID=$(curl -sX POST "$BASE/v1/evo/datasets" \
  -H "$JSON" \
  -d "{\"thread_id\":\"$THREAD_ID\",\"kb_id\":\"KB_ID\",\"eval_name\":\"demo_eval\"}" | jq -r .task_id)

EVAL_TASK_ID=$(curl -sX POST "$BASE/v1/evo/evals" \
  -H "$JSON" \
  -d "{\"thread_id\":\"$THREAD_ID\",\"dataset_id\":\"demo_eval\",\"target_chat_url\":\"http://localhost:8000/chat\"}" | jq -r .task_id)

RUN_ID=$(curl -sX POST "$BASE/v1/evo/runs" \
  -H "$JSON" \
  -d "{\"thread_id\":\"$THREAD_ID\"}" | jq -r .task_id)

# Replace REPORT_ID with the report_id from the run task payload after it succeeds.
APPLY_ID=$(curl -sX POST "$BASE/v1/evo/applies" \
  -H "$JSON" \
  -d "{\"thread_id\":\"$THREAD_ID\",\"report_id\":\"REPORT_ID\"}" | jq -r .task_id)

MERGE_ID=$(curl -sX POST "$BASE/v1/evo/applies/$APPLY_ID/accept?auto_next=merge" | jq -r .data.next_task_id)

DEPLOY_ID=$(curl -sX POST "$BASE/v1/evo/deploys" \
  -H "$JSON" \
  -d "{\"thread_id\":\"$THREAD_ID\",\"merge_id\":\"$MERGE_ID\"}" | jq -r .task_id)

ABTEST_ID=$(curl -sX POST "$BASE/v1/evo/abtests" \
  -H "$JSON" \
  -d "{\"thread_id\":\"$THREAD_ID\",\"apply_id\":\"$APPLY_ID\",\"baseline_eval_id\":\"BASELINE_EVAL_ID\",\"dataset_id\":\"demo_eval\"}" | jq -r .task_id)
```

## State Machine

Terminal statuses:

```text
dataset_gen: succeeded, failed_permanent, cancelled
eval:        succeeded, failed_permanent, cancelled
run:         succeeded, failed_permanent, cancelled
apply:       accepted, rejected, failed_permanent, cancelled
merge:       merged, failed_permanent, cancelled
deploy:      deployed, failed_permanent, cancelled
abtest:      succeeded, failed_permanent, cancelled
```

Common lifecycle:

```text
queued -> running -> succeeded
queued -> running -> stopping -> paused -> running (continue)
queued -> running -> failed_transient -> running (continue, apply/deploy only)
queued -> running -> failed_permanent
queued/running/paused/failed_transient -> cancelled
```

Flow-specific transitions:

```text
apply:  succeeded -> accepted | rejected
merge:  running -> merged (failure → failed_permanent, no retry)
deploy: running -> deployed (failure → failed_transient, retry via continue)
```

`merge` always fails permanent; `apply` and `deploy` support `continue` from
`paused` or `failed_transient`.

## Configuration

Environment variables read by `load_config()`:

| Variable | Default |
| --- | --- |
| `EVO_BASE_DIR` | `<repo>/LazyRAG/data/evo` |
| `EVO_DATA_DIR` | `<repo>/LazyRAG/evo/data` |
| `EVO_BADCASE_SCORE_FIELD` | `answer_correctness` |
| `EVO_CODE_MAP` | empty |
| `EVO_CHAT_SOURCE` | `<repo>/algorithm/chat` |
| `EVO_LLM_ROLE` | `evo_llm` |
| `EVO_EMBED_ROLE` | `evo_embed` |
| `EVO_AUTO_USER_ROLE` | `evo_llm` |
| `EVO_KB_BASE_URL` | `http://localhost:8055` |
| `EVO_CHUNK_BASE_URL` | `http://localhost:8055` |
| `EVO_DATASETGEN_MAX_WORKERS` | `5` |
| `EVO_DEPLOY_ADAPTER` | `none` |
| `EVO_DEPLOY_ADAPTER_BASE_URL` | empty |
| `EVO_EVAL_PROVIDER` | empty |
| `EVO_EVAL_BASE_URL` | empty |
| `EVO_EVAL_TOKEN` | empty |
| `EVO_EVAL_MOCK_PATH` | empty |
| `EVO_PROFILE` | `dev` |
| `EVO_ADMIN_TOKEN` | required for global stop/cancel |
| `LAZYRAG_MODEL_CONFIG_PATH` | chat model config path |
| `LAZYRAG_USE_INNER_MODEL` | `false` |

## Operations

```bash
# Reset a stuck worktree.
git -C ./LazyRAG/data/evo/git/chat.git worktree prune

# Reset opencode auth.
curl -sX DELETE "$BASE/v1/evo/admin/opencode/config" | jq .

# Wipe evo runtime state. The service recreates directories on startup.
rm -rf ./LazyRAG/data/evo

# Refresh chat baseline for apply.
rm -rf ./LazyRAG/data/evo/git/chat.git
```
