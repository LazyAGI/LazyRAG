# LazyRAG CLI

A command-line tool for algorithm engineers to manage knowledge bases and ingest documents through the full LazyRAG service stack (with authentication).

## Prerequisites

- The LazyRAG service stack is running (Kong gateway at `http://localhost:8000`)
- Python 3.9+

## Quick start

```bash
# 1. Register and auto-login
./lazyrag register -u alice -p mypassword

# 2. Create a knowledge base
./lazyrag kb-create --name "project-docs"

# 3. Upload a directory of documents and wait for parsing
./lazyrag upload --dataset <dataset_id> --dir ./my-docs --extensions pdf,docx --wait

# 4. Check task status
./lazyrag task-list --dataset <dataset_id>
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

## Knowledge base management

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
./lazyrag kb-list [--page-size 100] [--json]
```

## Document upload

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

## Task management

### List tasks

```bash
./lazyrag task-list --dataset <dataset_id> [--page-size 100] [--json]
```

### Get task details

```bash
./lazyrag task-get --dataset <dataset_id> <task_id>
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

## File structure

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
    ├── dataset.py       # kb-create, kb-list
    └── upload.py        # upload, task-list, task-get
lazyrag                  # bash wrapper script
tests/test_cli.py        # unit tests
```

## Known limitations

- **Directory nesting**: Only top-level folders are created from upload paths. Deeper nesting is not reconstructed server-side.
- **Test coverage**: Current tests are unit-level only. End-to-end flows (auth refresh, batchUpload -> start -> wait) are not yet covered by automated tests and require manual integration testing against a running stack.
- **No retry on upload**: Individual file upload failures are reported but not retried. Re-run the command to retry failed files.
