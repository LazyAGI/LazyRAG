# LazyRAG CLI

LazyRAG 的命令行入口，面向算法同学和 code agent，覆盖认证、知识库管理、文档导入、任务检查、分块查看和检索验证。

## Prerequisites

- LazyRAG 服务栈已启动，Kong 网关默认在 `http://localhost:8000`
- 如果要使用默认 `retrieve` 本地模式，需保证本地 `lazyllm-algo` 容器正在运行
- Python 3.9+

## Quick Start

最短闭环：

```bash
# 1. 注册并自动登录
./lazyrag register -u alice -p mypassword

# 2. 创建知识库，并自动设为当前默认 dataset
./lazyrag kb-create --name "project-docs" --dataset-id project-docs

# 3. 查看当前上下文
./lazyrag status

# 4. 导入目录并等待解析完成
./lazyrag upload --dir ./my-docs --extensions pdf,docx,txt --wait

# 5. 查看文档和任务
./lazyrag doc-list
./lazyrag task-list

# 6. 查看某个文档切块
./lazyrag chunk <document_id> --json

# 7. 做一次检索验证
./lazyrag config set algo_dataset general_algo
./lazyrag retrieve '介绍一下解析链路' --json
```

如果你不想每次都传 `--dataset`，可以直接用：

```bash
./lazyrag use project-docs
```

之后大部分 dataset 相关命令都会默认使用当前 dataset。

## Example Flows

### Flow 1: 新建知识库并导入本地目录

```bash
./lazyrag register -u algo_demo -p 'Passw0rd!'
./lazyrag kb-create --name 'Parser Smoke' --dataset-id parser-smoke
./lazyrag upload --dir ./docs --extensions pdf,md,txt --wait
./lazyrag task-list --json
./lazyrag doc-list --json
```

### Flow 2: 绑定当前 dataset，后续命令不再传 `--dataset`

```bash
./lazyrag use parser-smoke
./lazyrag status
./lazyrag upload --dir ./more-docs --wait
./lazyrag task-get <task_id>
./lazyrag doc-list
```

### Flow 3: 查看文档切块并测试检索

```bash
./lazyrag doc-list --json
./lazyrag chunk <document_id> --page-size 5 --json

# 设置默认 algo dataset，后续 retrieve 可省略 --dataset
./lazyrag config set algo_dataset general_algo

# 默认模式：本地会优先进入 lazyllm-algo 容器执行检索
./lazyrag retrieve '介绍一下解析链路'

# 指定配置文件，按 runtime_models YAML 中的 retrieval 配置执行
./lazyrag retrieve '介绍一下解析链路' \
  --config /Users/chenjiahao/Desktop/codes/LazyRAG/algorithm/chat/runtime_models.yaml \
  --json
```

### Flow 4: 清理文档和知识库

```bash
./lazyrag doc-delete <document_id> -y
./lazyrag kb-delete -y
```

## Authentication

The CLI communicates through the Kong API gateway and requires a valid user session. Credentials are stored locally at `~/.lazyrag/credentials.json` with `0600` permissions.

Token refresh is automatic: when the access token expires, the CLI uses the stored refresh token to obtain a new one. If the refresh token is also expired, the CLI prompts you to log in again.

### Register

```bash
./lazyrag register -u <username> -p <password> [--email user@example.com] [--no-login]
```

Creates a new user account. By default, auto-logs in after registration. Use `--no-login` to skip.

### Login

```bash
./lazyrag login -u <username> -p <password>
```

If `-u` or `-p` are omitted, the CLI will prompt interactively (password input is hidden).

### Logout

```bash
./lazyrag logout
```

Revokes the refresh token server-side (best-effort) and removes local credentials.

### Whoami

```bash
./lazyrag whoami [--json]
```

Shows current user info (user_id, username, role, status).

## Context And Config

### Use

```bash
./lazyrag use <dataset_id>
```

将某个 dataset 设为当前默认值，后续 `upload / task-* / doc-* / chunk` 都可以省略 `--dataset`。

### Status

```bash
./lazyrag status [--json]
```

输出当前 CLI 上下文，包括：

- 当前 server
- 是否已登录
- 当前 username / role
- 当前默认 dataset
- 当前 `algo_url`
- 当前 `algo_dataset`

### Config

```bash
./lazyrag config list [--json]
./lazyrag config get <key>
./lazyrag config set <key> <value>
./lazyrag config unset <key>
```

当前支持的常用 key：

- `dataset`
- `algo_url`
- `algo_dataset`

示例：

```bash
./lazyrag config set algo_dataset general_algo
./lazyrag config set algo_url http://localhost:8001
./lazyrag config list
```

## Knowledge Base Management

In LazyRAG, a "knowledge base" maps to a "dataset" in the core service API.

### Create

```bash
./lazyrag kb-create --name "My KB" [--desc "description"] [--algo-id my_algo] [--dataset-id custom-id]
```

- `--name` (required): Display name for the knowledge base.
- `--dataset-id`: Specify a custom dataset ID. Auto-generated if omitted.
- `--algo-id`: Algorithm ID to associate. Defaults to `__default__`.

### List

```bash
./lazyrag kb-list [--page-size 20] [--page 2] [--json]
```

### Delete

```bash
./lazyrag kb-delete [--dataset <dataset_id>] -y [--json]
```

如果不传 `--dataset`，会删除当前 `lazyrag use` 选中的 dataset。

## Document Upload

### Upload a directory

```bash
./lazyrag upload --dataset <dataset_id> --dir <path> [options]
```

Scans a local directory and uploads all matching files into the target dataset. Each file is uploaded via the `batchUpload` endpoint which creates both the file record and the parse task in a single request.

**Options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--extensions` | all | Comma-separated suffixes to include, e.g. `pdf,docx,txt` |
| `--limit` | unlimited | Max number of files to upload |
| `--recursive` / `--no-recursive` | recursive | Whether to scan subdirectories |
| `--include-hidden` | false | Include hidden files/directories (starting with `.`) |
| `--wait` | false | Block until all parse tasks complete |
| `--wait-interval` | 3.0s | Polling interval when `--wait` is set |
| `--wait-timeout` | 0 (no limit) | Max seconds to wait; 0 means wait indefinitely |
| `--timeout` | 300s | HTTP timeout per file upload |

**Directory structure handling:**

When uploading files from nested directories, the CLI sends the relative path to the server. The server uses the **first path segment** to create a top-level folder in the dataset. Deeper nesting is not reconstructed as nested folders; files from `reports/q1/summary.pdf` will appear under folder `reports`.

**Example:**

```bash
# Upload all PDFs and DOCX files, wait for parsing to finish
./lazyrag upload --dataset ds-abc123 --dir ./documents --extensions pdf,docx --wait

# Upload only top-level files (no recursion), limit to 10
./lazyrag upload --dataset ds-abc123 --dir ./documents --no-recursive --limit 10
```

## Task Management

### List tasks

```bash
./lazyrag task-list [--dataset <dataset_id>] [--page-size 20] [--json]
```

### Get task details

```bash
./lazyrag task-get [--dataset <dataset_id>] <task_id>
```

## Document Management

### List documents

```bash
./lazyrag doc-list [--dataset <dataset_id>] [--page-size 20] [--json]
```

### Update document metadata

```bash
./lazyrag doc-update [--dataset <dataset_id>] <document_id> \
  --name 'new-name.txt' \
  --meta '{"source":"manual-check"}'
```

### Delete document

```bash
./lazyrag doc-delete [--dataset <dataset_id>] <document_id> -y
```

## Chunk Inspection

```bash
./lazyrag chunk [--dataset <dataset_id>] <document_id> [--page-size 20] [--page 2] [--json]
```

适合快速确认解析后的切块内容是否符合预期。

## Retrieval Smoke Test

### Default mode

```bash
./lazyrag retrieve '介绍一下解析链路'
```

默认行为：

- 若显式传了 `--url`，直接连指定 algo service
- 若本地配置了 `algo_url`，优先使用该地址
- 否则会尝试自动找到本地运行中的 `lazyllm-algo` 容器，在容器内执行检索

### Common options

```bash
./lazyrag retrieve '介绍一下解析链路' \
  --dataset general_algo \
  --group-name block \
  --topk 6 \
  --similarity cosine \
  --embed-keys embed_1 \
  --json
```

### Runtime model config

```bash
./lazyrag retrieve '介绍一下解析链路' \
  --config /Users/chenjiahao/Desktop/codes/LazyRAG/algorithm/chat/runtime_models.yaml \
  --json
```

## Configuration

### Server URL

The CLI connects to `http://localhost:8000` by default (the Kong gateway). Override with:

- `--server URL` flag on any command
- `LAZYRAG_SERVER_URL` environment variable
- The `server_url` stored in credentials after login

Priority: `--server` flag > stored credentials > environment variable > default.

### Credentials location

Override the default `~/.lazyrag/` directory by setting `LAZYRAG_HOME`:

```bash
export LAZYRAG_HOME=/custom/path
./lazyrag login -u alice -p pass
# Credentials stored at /custom/path/credentials.json
```

## Architecture

```
CLI (lazyrag)
  |
  v
Kong API Gateway (:8000)
  |-- /api/authservice/*  -->  auth-service (FastAPI)
  |-- /api/core/*         -->  core service (Go)
                                  |
                                  v
                           doc-server / parse-server / parse-worker
```

The CLI uses Python's stdlib `urllib` with no external dependencies. All requests go through the Kong gateway which handles RBAC authorization via JWT tokens.

## File Structure

```
cli/
├── __init__.py
├── __main__.py         # python -m cli entry point
├── main.py             # argparse definitions and command dispatch
├── config.py           # server URL, credential paths, API prefixes
├── credentials.py      # token persistence (~/.lazyrag/credentials.json)
├── client.py           # HTTP client with Bearer token injection and refresh
└── commands/
    ├── __init__.py
    ├── auth.py          # register, login, logout, whoami
    ├── chunk.py         # chunk inspection
    ├── context.py       # use, status, config
    ├── dataset.py       # kb-create, kb-list, kb-delete
    ├── doc.py           # doc-list, doc-update, doc-delete
    ├── retrieve.py      # retrieval smoke test
    └── upload.py        # upload, task-list, task-get
lazyrag                  # bash wrapper script
tests/test_cli.py        # unit tests
```

## Known Limitations

- **Directory nesting**: Only top-level folders are created from upload paths. Deeper nesting is not reconstructed server-side.
- **Retrieve local mode**: Default `retrieve` is optimized for local compose/developer environments. In CI or remote deployment, prefer explicit `--url`.
- **Test coverage**: Current tests are still mainly unit-level. End-to-end flows require manual integration testing against a running stack.
- **No retry on upload**: Individual file upload failures are reported but not retried. Re-run the command to retry failed files.
