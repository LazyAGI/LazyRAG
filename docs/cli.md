# LazyRAG CLI 操作手册

`lazyrag` 是 LazyRAG 的命令行入口，面向算法同学和 code agent，覆盖认证、知识库管理、目录导入、任务检查、文档查看、切块检查、检索验证、上传恢复与回滚。

如果你的目标是”尽快把一批文件导入知识库，然后确认解析和检索结果是否正常”，优先看”首次使用”和”常见场景”两节。

`upload` 是状态感知的命令：每次运行都会在 `~/.lazyrag/runs/<run_id>/` 留下 manifest/state/result 三份文件，支持去重跳过、中断恢复、仅重跑失败项，以及通过 `run-undo` 一键回滚。

## 1. 使用前准备

- LazyRAG 服务栈已启动，默认通过 Kong 网关访问：`http://localhost:8000`
- 如果要使用默认 `retrieve` 本地模式，需要本地 `lazyllm-algo` 容器处于运行状态
- Python 3.9+

## 2. 首次使用

下面这组命令是最短闭环：注册、建库、上传、检查、检索。

```bash
# 1. 注册并自动登录
./lazyrag register -u alice -p mypassword

# 2. 创建知识库，并自动设为当前默认 dataset
./lazyrag kb-create --name 'project-docs' --dataset-id project-docs

# 3. 查看当前上下文
./lazyrag status

# 4. 上传目录并等待解析完成
./lazyrag upload --dir ./my-docs --extensions pdf,docx,txt --wait

# 5. 查看任务和文档
./lazyrag task-list
./lazyrag doc-list

# 6. 查看某个文档的切块结果
./lazyrag chunk <document_id> --json

# 7. 做一次检索验证
./lazyrag config set algo_dataset general_algo
./lazyrag retrieve '介绍一下解析链路' --json
```

如果这个知识库创建时使用了自定义 `--algo-id`，这里的 `algo_dataset` 也要设置成同一个值；`general_algo` 只适用于默认算法。

如果你已经有 dataset，也可以先切换默认上下文：

```bash
./lazyrag use project-docs
```

之后大多数带 `--dataset` 的命令都可以省略这个参数。

## 3. 常见使用场景

### 场景一：新建知识库并导入一批文件

```bash
./lazyrag register -u algo_demo -p 'Passw0rd!'
./lazyrag kb-create --name 'Parser Smoke' --dataset-id parser-smoke
./lazyrag upload --dir ./docs --extensions pdf,md,txt --wait
./lazyrag task-list --json
./lazyrag doc-list --json
```

适用于第一次跑通解析链路，确认文件是否成功入库。

### 场景二：绑定默认知识库，后续命令不再重复传参

```bash
./lazyrag use parser-smoke
./lazyrag status
./lazyrag upload --dir ./more-docs --wait
./lazyrag task-get <task_id>
./lazyrag doc-list
```

适合长期盯一个 dataset 做反复调试。

### 场景三：检查解析结果是否符合预期

```bash
./lazyrag doc-list --json
./lazyrag chunk <document_id> --page-size 5 --json
```

常见检查点：

- 文档名是否正确
- 文档是否进入 `SUCCESS`
- 切块内容是否完整
- 切块粒度是否符合预期

### 场景四：做一次检索 smoke test

```bash
# 设置默认 algo dataset ID，后续 retrieve 可省略 --algo-dataset
./lazyrag config set algo_dataset general_algo

# 默认模式：本地优先进入 lazyllm-algo 容器执行检索
# 检索时会自动携带当前 dataset 作为 kb_id 过滤条件
./lazyrag retrieve '介绍一下解析链路'

# 指定 runtime_models 配置文件执行检索
./lazyrag retrieve '介绍一下解析链路' \
  --config ./algorithm/chat/runtime_models.yaml \
  --json
```

适合在修改解析、embedding 或 retriever 配置后做快速回归。

### 场景五：清理数据

```bash
./lazyrag doc-delete <document_id> -y
./lazyrag kb-delete -y
```

如果 `kb-delete` 不传 `--dataset`，默认删除当前 `use` 选中的 dataset。

### 场景六：传错目录想整批干掉

```bash
# 找到那次 run
./lazyrag run-list

# 回滚这次 run 上传的所有 document
./lazyrag run-undo <run_id> -y
```

`run-undo` 会删除该 run 创建的所有 document，同时清理本地 uploaded 索引。

### 场景七：漏了几个文件想补上

```bash
# 把新文件放进目录，直接再跑一次即可
./lazyrag upload --dir ./docs --wait
```

去重基于 `relative_path + size + mtime`，已存在且未变化的文件会自动跳过（identical existing 永远 skipped）。

### 场景八：改了几个文件想重传

```bash
./lazyrag upload --dir ./docs --replace-changed --wait
```

CLI 把 mtime/size 变化的文件归为 `changed`，`--replace-changed` 会先删除远端旧 document 再上传新版本。

### 场景九：上传过程中断，想继续

```bash
# 上次被 Ctrl-C 中断，终端提示了 run_id
./lazyrag upload --resume <run_id>
```

恢复会跳过已成功的文件，只处理剩余的 pending 项。

### 场景十：只重跑上次失败的

```bash
./lazyrag upload --retry-failed --wait
```

会自动找到该 dataset 最近一次 run 里的 `failed` 文件，单独组成新 run 重试。

## 4. 认证与登录

CLI 通过 Kong 网关访问服务，需要先登录。凭证默认保存在 `~/.lazyrag/credentials.json`，文件权限为 `0600`。

`access_token` 过期后，CLI 会自动使用 `refresh_token` 刷新；如果刷新也失败，需要重新登录。

### 注册

```bash
./lazyrag register -u <username> -p <password> [--email user@example.com] [--no-login]
```

默认注册后自动登录；如果只想创建账号、不登录，加 `--no-login`。

### 登录

```bash
./lazyrag login -u <username> -p <password>
```

如果不传 `-u` 或 `-p`，CLI 会进入交互式输入，密码输入不回显。

### 登出

```bash
./lazyrag logout
```

会尽力调用服务端登出接口，并删除本地保存的凭证。

### 查看当前用户

```bash
./lazyrag whoami [--json]
```

## 5. 上下文与配置

### use

```bash
./lazyrag use <dataset_id>
```

将某个 dataset 设为当前默认值，后续 `upload / task-* / doc-* / chunk` 都可以省略 `--dataset`。

### status

```bash
./lazyrag status [--json]
```

会输出当前 CLI 上下文，包括：

- 当前 server
- 是否已登录
- 当前 username / role
- 当前默认 dataset
- 当前 `algo_url`
- 当前 `algo_dataset`

### config

```bash
./lazyrag config list [--json]
./lazyrag config get <key>
./lazyrag config set <key> <value>
./lazyrag config unset <key>
```

常用配置项：

- `dataset`
- `algo_url`
- `algo_dataset`

示例：

```bash
./lazyrag config set algo_dataset general_algo
./lazyrag config set algo_url http://localhost:8001
./lazyrag config list
```

## 6. 知识库管理

在 LazyRAG 里，CLI 对外叫“知识库”，对应 core service API 里的 `dataset`。

### 新建知识库

```bash
./lazyrag kb-create --name 'My KB' [--desc 'description'] [--algo-id my_algo] [--dataset-id custom-id]
```

说明：

- `--name` 必填，知识库展示名
- `--dataset-id` 可选，显式指定 dataset ID；不传则自动生成
- `--algo-id` 可选，关联算法 ID；默认取本地 `algo_dataset` 配置或环境变量，通常是 `general_algo`

### 列出知识库

```bash
./lazyrag kb-list [--page-size 20] [--page 2] [--json]
```

### 删除知识库

```bash
./lazyrag kb-delete [--dataset <dataset_id>] -y [--json]
```

## 7. 目录上传与任务查看

`upload` 是状态感知的批量导入命令，支持去重、中断恢复、失败重试。每次运行都会在 `~/.lazyrag/runs/<run_id>/` 留下完整记录。

### 三种模式

`upload` 必须指定一种模式（`--dir` / `--resume` / `--retry-failed` 三选一）：

```bash
# 模式一：扫一个新目录
./lazyrag upload --dir ./docs --wait

# 模式二：恢复上次中断的 run
./lazyrag upload --resume <run_id>
./lazyrag upload --resume /abs/path/to/manifest.json

# 模式三：只重跑该 dataset 最近一次 run 的失败项
./lazyrag upload --retry-failed --wait
```

### 参数速查

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--dir` / `--directory` | 无 | 要上传的本地目录 |
| `--resume` | 无 | 恢复指定 run（`run_id` 或 manifest 绝对路径） |
| `--retry-failed` | 无 | 仅重跑最近一次 run 的失败项 |
| `--extensions` | 全部后缀 | 逗号分隔，例如 `pdf,docx,txt` |
| `--limit` | 不限制 | 最多上传多少个文件 |
| `--recursive` / `--no-recursive` | 递归扫描 | 是否扫描子目录 |
| `--include-hidden` | `false` | 是否包含隐藏文件和隐藏目录 |
| `--replace-changed` | `false` | 对 `changed` 文件先删除旧 doc 再上传 |
| `--wait` | `false` | 阻塞等待所有解析任务结束 |
| `--wait-interval` | `3.0s` | `--wait` 模式下的轮询间隔 |
| `--wait-timeout` | `0` | 最长等待秒数，`0` 表示一直等 |
| `--timeout` | `300s` | 单个文件上传请求超时 |
| `--report-json <path>` | 无 | 额外输出机器可读报告到文件 |
| `--json` | `false` | stdout 输出结构化结果 |

### 去重分类规则

`upload` 在正式上传前会比对三处信号：

- 本地扫描结果（`relative_path + size + mtime`）
- 远端 `doc-list`（`relative_path + document_size`）
- 本地 uploaded 索引 `~/.lazyrag/datasets/<dataset_id>/uploaded.json`（`size + mtime`）

分类规则：

- `new`：远端无该路径，或远端 doc 状态是 `FAILED` → 直接上传
- `changed`：远端有该路径但 size 不一致，或本地索引中的 size/mtime 与当前不一致 → 默认**不上传**并打印警告，除非传 `--replace-changed`
- `existing`：远端健康且 size 一致 → **总是 skipped**（identical 文件没有重传的理由）

跨 run 索引 (`~/.lazyrag/datasets/<ds>/uploaded.json`) 只会在任务真正 SUCCESS 后才写入。解析失败的 document 不会污染索引，下次运行会正确地重新上传。

### 示例

```bash
# 第一次上传（尚未登录就要先 login）
./lazyrag upload --dir ./documents --extensions pdf,docx --wait

# 追加新文件（identical existing 自动 skipped）
./lazyrag upload --dir ./documents --wait

# 覆盖被修改的文件
./lazyrag upload --dir ./documents --replace-changed --wait

# 只重跑失败的
./lazyrag upload --retry-failed --wait

# 恢复中断的 run（KeyboardInterrupt 后终端会显示 run_id）
./lazyrag upload --resume 20260414T163045-ds_abc123

# 额外写机器可读报告
./lazyrag upload --dir ./documents --wait --report-json /tmp/report.json --json
```

### 本地 run 目录结构

```text
~/.lazyrag/
├── datasets/<dataset_id>/
│   └── uploaded.json          # 跨 run 的 uploaded 索引
└── runs/<run_id>/             # 每次 upload 一个目录
    ├── manifest.json          # 扫目录快照
    ├── state.json             # 实时进度（uploaded/skipped/failed/...）
    └── result.json            # 最终总结
```

每上传一个文件都会原子地更新 `state.json`，即使 Ctrl-C 也能安全 `--resume`。

### 目录层级处理说明

CLI 会把文件的相对路径传给服务端，但当前服务端只会根据 `relative_path` 的第一层路径创建一个顶层文件夹。

这意味着：

- `reports/q1/summary.pdf` 会进入顶层文件夹 `reports`
- 不会在服务端重建成 `reports/q1/summary.pdf` 这样的完整嵌套目录树

如果你依赖完整目录层级，请不要把当前行为当成已支持能力。

### 查看任务列表

```bash
./lazyrag task-list [--dataset <dataset_id>] [--page-size 20] [--json]
```

### 查看单个任务详情

```bash
./lazyrag task-get [--dataset <dataset_id>] <task_id>
```

### 取消运行中的任务

```bash
./lazyrag task-cancel <task_id> [--dataset <dataset_id>] [--json]
```

对应后端 `:suspend` 端点，实际会把任务状态转为 `CANCELED`。

### 恢复被挂起的任务

```bash
./lazyrag task-resume <task_id> [--dataset <dataset_id>] [--json]
```

仅对 `SUSPENDED` 态任务有效；对 `CANCELED` 任务的行为由后端决定。

## 8. 上传 run 管理

每次 `upload` 都是一个 run，本地状态存放在 `~/.lazyrag/runs/<run_id>/`。通过 `run-list` / `run-undo` 查看历史和回滚。

### 列出历史 run

```bash
./lazyrag run-list                    # 当前默认 dataset 的 run
./lazyrag run-list --dataset <id>     # 指定 dataset
./lazyrag run-list --all              # 所有 dataset
./lazyrag run-list --json
```

每行会显示 `run_id / status / uploaded / failed / created_at / dataset`。

### 回滚一次 run

```bash
./lazyrag run-undo <run_id> [-y] [--json]
```

`run-undo` 会：

1. 读 `~/.lazyrag/runs/<run_id>/state.json`
2. 对每个已上传的 `document_id` 调用 `DELETE /datasets/{ds}/documents/{doc_id}`
3. 从本地 `uploaded.json` 索引中移除对应条目
4. 把该 run 的 `status` 标为 `undone`

单个删除失败时会继续处理剩余，最后汇总打印错误项。

## 9. 文档与切块检查

### 查看文档列表

```bash
./lazyrag doc-list [--dataset <dataset_id>] [--page-size 20] [--json]
```

### 修改文档元信息

```bash
./lazyrag doc-update [--dataset <dataset_id>] <document_id> \
  --name 'new-name.txt' \
  --meta '{"source":"manual-check"}'
```

### 删除文档

```bash
./lazyrag doc-delete [--dataset <dataset_id>] <document_id> -y
```

### 查看切块

```bash
./lazyrag chunk [--dataset <dataset_id>] <document_id> [--page-size 20] [--page 2] [--json]
```

适合用于确认解析后的 `segments / total_size / 内容片段` 是否符合预期。

## 10. 检索验证

### 最简单的用法

```bash
./lazyrag retrieve '介绍一下解析链路'
```

默认行为是：

- 如果显式传了 `--url`，直接访问指定 algo service
- 如果本地配置了 `algo_url`，优先使用该地址
- 否则尝试自动找到本地运行中的 `lazyllm-algo` 容器，并在容器内执行检索
- 远程 `Document` 默认使用 `algo_dataset` 配置，通常是 `general_algo`
- 当前知识库通过 `kb_id=<dataset_id>` 作为过滤条件传给 retriever
- 如果知识库创建时指定了自定义 `algo_id`，需要把 `algo_dataset` 配置成相同值

### 常用参数

```bash
./lazyrag retrieve '介绍一下解析链路' \
  --dataset project-docs \
  --algo-dataset general_algo \
  --group-name block \
  --topk 6 \
  --similarity cosine \
  --embed-keys embed_1 \
  --json
```

### 使用 runtime_models 配置文件

```bash
./lazyrag retrieve '介绍一下解析链路' \
  --config ./algorithm/chat/runtime_models.yaml \
  --json
```

这个模式适合验证某份 `runtime_models.yaml` 中定义的检索配置是否真的能跑通。

## 11. 环境配置

### Server 地址

CLI 默认连接 `http://localhost:8000`。覆盖方式如下：

- 任意命令显式传 `--server URL`
- 设置环境变量 `LAZYRAG_SERVER_URL`
- 使用登录后保存在本地凭证里的 `server_url`

优先级：

`--server` > 本地凭证中的 `server_url` > `LAZYRAG_SERVER_URL` > 默认值

### 凭证目录

如果不想使用默认的 `~/.lazyrag/`，可以设置 `LAZYRAG_HOME`：

```bash
export LAZYRAG_HOME=/custom/path
./lazyrag login -u alice -p pass
```

此时凭证会写入 `/custom/path/credentials.json`。

## 12. 命令速查

### 认证

```bash
./lazyrag register -u <username> -p <password>
./lazyrag login -u <username> -p <password>
./lazyrag logout
./lazyrag whoami
```

### 上下文

```bash
./lazyrag use <dataset_id>
./lazyrag status
./lazyrag config list
./lazyrag config get <key>
./lazyrag config set <key> <value>
./lazyrag config unset <key>
```

### 知识库

```bash
./lazyrag kb-create --name 'My KB'
./lazyrag kb-list
./lazyrag kb-delete -y
```

### 上传与任务

```bash
./lazyrag upload --dir ./docs --wait
./lazyrag upload --dir ./docs --replace-changed --wait
./lazyrag upload --resume <run_id>
./lazyrag upload --retry-failed --wait
./lazyrag task-list
./lazyrag task-get <task_id>
./lazyrag task-cancel <task_id>
./lazyrag task-resume <task_id>
```

### 上传 run 管理

```bash
./lazyrag run-list
./lazyrag run-list --all
./lazyrag run-undo <run_id> -y
```

### 文档与切块

```bash
./lazyrag doc-list
./lazyrag doc-update <document_id> --name 'new-name.txt'
./lazyrag doc-delete <document_id> -y
./lazyrag chunk <document_id> --json
```

### 检索

```bash
./lazyrag retrieve '介绍一下解析链路'
./lazyrag retrieve '介绍一下解析链路' --topk 10 --group-name block --json
./lazyrag retrieve '介绍一下解析链路' --url http://algo:8000 --algo-dataset general_algo
./lazyrag retrieve '介绍一下解析链路' --config /path/to/runtime_models.yaml
```

## 13. 系统链路说明

```text
CLI (lazyrag)
  |
  v
Kong API Gateway (:8000)
  |-- /api/authservice/*  --> auth-service (FastAPI)
  |-- /api/core/*         --> core service (Go)
                                 |
                                 v
                          doc-server / parse-server / parse-worker
```

CLI 基于 Python 标准库 `urllib` 实现，没有引入额外依赖；所有请求都通过 Kong 网关，鉴权依赖 JWT。

## 14. 代码目录

```text
cli/
├── __init__.py
├── __main__.py
├── main.py
├── config.py
├── credentials.py
├── context.py
├── upload_state.py        # run 目录 + uploaded 索引 + dedup 分类
├── client.py
└── commands/
    ├── __init__.py
    ├── auth.py
    ├── chunk.py
    ├── context.py
    ├── dataset.py
    ├── doc.py
    ├── retrieve.py
    ├── run.py             # run-list, run-undo
    ├── task.py            # task-cancel, task-resume
    └── upload.py
lazyrag
tests/test_cli.py
```

## 15. 已知边界

- 上传目录时，服务端只会按第一层路径创建顶层文件夹，不支持完整嵌套目录重建
- 默认 `retrieve` 本地模式更适合本地 compose 或开发环境；远程部署场景建议显式传 `--url`
- 当前测试仍以单测为主，完整端到端行为仍需要结合真实运行栈做集成验证
- 上传失败项不会自动重试，需要用 `lazyrag upload --retry-failed` 或 `--resume` 手动触发
- 本地 run 目录不会自动清理，`~/.lazyrag/runs/` 需要用户自行清理（没有内置 `runs prune` 命令）
- 后端 `task-cancel` 实际对应 `:suspend` 端点，转移到 `CANCELED` 态，不是真正的暂停；`task-resume` 只对 `SUSPENDED` 态任务有效
- dedup 信号源：远端 `doc-list` 只能提供 `relative_path + document_size`，精到 `mtime` 的判断依赖本地 `~/.lazyrag/datasets/<ds>/uploaded.json` 索引。首次在一台新机器上对一个已有 dataset 运行 `upload`，所有文件会被保守地归为 `existing`（除非远端 doc 状态是 FAILED）
- 跨 run 索引只会在任务真正 SUCCESS 之后才写入：非 `--wait` 模式下 `uploaded.json` 不会更新，下次运行 dedup 退化为"所有文件都没有本地索引"的保守态
- 当前 CLI 是单机串行上传，没有 `--jobs` 并发（规划中）
