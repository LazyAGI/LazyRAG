# LazyRAG

**[English](README.md)** | **中文**

基于 Kong API 网关的全栈应用：JWT/RBAC 认证、Go 核心 API、Python 算法服务（文档解析、RAG 对话）及简易 Web 前端。

## 架构概览

- **Kong**（端口 8000）：声明式配置的 API 网关；将 `/api/auth`、`/api/chat`、`/api` 路由到后端；受保护路由使用 RBAC 插件。
- **前端**（端口 8080）：静态单页（nginx），登录、刷新 Token、对话界面，请求经 Kong 转发。
- **auth-service**：FastAPI 认证服务，注册、登录、刷新、角色与权限、引导创建管理员；Kong 的 `rbac-auth` 插件调用该服务。
- **core**：Go HTTP 服务，提供数据集、文档、任务、检索等接口（当前多为桩实现）；经 Kong 并启用 RBAC。
- **算法栈**：
  - **mineru**：PDF 解析（MinerU）。
  - **processor-server** / **processor-worker**：文档任务队列与处理。
  - **parsing**：文档服务（lazyllm RAG），向量库（Milvus）、分段存储（OpenSearch）、MinerU 阅读器。
  - **chat**：RAG 对话 API（lazyllm），端口 8046；依赖 parsing 文档服务。

- **PostgreSQL**（db）：供 auth-service 与 processor 存储应用数据与文档任务。

## 请求流程（验证链路）

用户请求从前端到后端依次经过以下验证环节：

```
前端
   │
   ├─► 1. auth-service（获取 JWT）
   │      登录/注册 → auth-service 返回 JWT → 前端存储 token
   │
   └─► 2. Kong（RBAC）
         携带 JWT 的 API 请求 → Kong rbac-auth 插件 → auth-service /api/auth/authorize
         → 校验 JWT 与路由权限 → 通过则转发
         │
         ▼
      3. 后端（core）— ACL + 函数调用
         core 接收请求 → ACL 校验（资源级，如 kb_id、dataset_id）
         → 执行 handler 或代理到算法服务
         │
         ▼
      4. 算法
         core 代理到 Python 服务（chat、parsing 等）进行 RAG / 文档处理
```

| 环节 | 组件 | 作用 |
|------|------|------|
| 1 | auth-service | 登录/注册时签发 JWT；前端存储 |
| 2 | Kong | RBAC：通过 auth-service authorize 校验 JWT 与路由权限 |
| 3 | core（后端） | ACL：资源级权限（kb、dataset）；handler 执行 |
| 4 | algorithm | RAG 对话、文档解析、任务处理 |

## 环境要求

- Docker 与 Docker Compose
- （可选）Go 1.22（backend/core）、Python 3.11+ 与 flake8，用于本地开发与 lint

## 快速开始

```bash
docker compose up --build
```

- 前端：http://localhost:8080  
- Kong（API）：http://localhost:8000  
- 默认管理员：`admin` / `admin`（由 auth-service 引导创建）

## 项目结构

```
LazyRAG/
├── kong.yml                    # Kong 声明式配置（路由、rbac-auth）
├── docker-compose.yml          # 所有服务
├── Makefile                    # 代码检查：flake8（algorithm、backend）、gofmt（backend/core）
├── backend/
│   ├── auth-service/          # FastAPI 认证、JWT、RBAC、引导
│   ├── core/                  # Go API（dataset、document、task、retrieval 等）
│   └── scripts/               # 如 extract_api_permissions 供 auth 使用
├── frontend/                  # nginx + index.html 单页
├── algorithm/
│   ├── chat/                  # RAG 对话（lazyllm）
│   ├── common/                # 共享工具（如 DB URL 解析）
│   ├── parsing/               # 文档服务（lazyllm、MinerU、Milvus、OpenSearch）
│   ├── processor/             # 文档任务 server + worker
│   ├── parsing/mineru.py      # MinerU PDF 服务
│   └── requirements.txt       # lazyllm[rag-advanced]
├── api/                       # OpenAPI 规范（集中管理）
│   ├── backend/core/           # core 服务 OpenAPI
│   ├── backend/auth-service/   # auth-service OpenAPI
│   └── algorithm/             # 算法服务 OpenAPI
├── kong/plugins/rbac-auth/     # Kong RBAC 插件（auth_service_url）
├── scripts/                   # 如 gen_openapi_rag.sh
└── tests/
    ├── backend/               # 后端测试
    └── algorithm/             # 算法测试
```

- **Go 模块**：`backend/core` 使用 `module lazyrag/core` 为刻意设计，缩短 import 路径。
- **OpenAPI**：规范集中存放在 `api/`，与各服务目录对应；新增路由时需同步更新。

## 环境变量（主要）

| 服务/范围       | 变量名                    | 说明 / 示例                          |
|-----------------|---------------------------|--------------------------------------|
| auth-service    | `DATABASE_URL`            | PostgreSQL 连接                      |
| auth-service    | `JWT_SECRET`、`JWT_TTL_MINUTES`、`JWT_REFRESH_TTL_DAYS` | Token 配置   |
| auth-service    | `BOOTSTRAP_ADMIN_*`       | 初始管理员账号                       |
| processor-*     | `DOC_TASK_DATABASE_URL`   | 文档任务用同一数据库                 |
| parsing         | `MILVUS_URI`、`OPENSEARCH_URI`、`OPENSEARCH_USER`、`OPENSEARCH_PASSWORD` | 向量与分段存储 |
| chat            | `DOCUMENT_SERVER_URL`、`MAX_CONCURRENCY` | 文档服务地址与并发数        |

若使用非默认的 Milvus/OpenSearch，可在 `docker-compose.yml` 或 env 文件中覆盖上述变量。

## 代码检查

```bash
make lint              # Python（algorithm、backend）+ Go（backend/core）
make lint-only-diff    # 仅对变更文件执行 lint（Python + Go）
```

Python 使用 flake8（通过 `.flake8` 排除子模块 `algorithm/lazyllm`）；Go 使用 `gofmt`。

## API 摘要

- **Kong**  
  - `POST /api/auth/*` → auth-service（登录、注册、刷新、角色、鉴权）。  
  - `POST /api/chat`、`POST /api/chat/stream` → chat 服务（不经 Kong RBAC：前端 → Kong → chat）。  
  - 其余 `/api/*` → core（经 Kong RBAC）。

- **auth-service**（via Kong）：登录、注册、刷新、角色、权限、用户角色分配、鉴权（方法 + 路径）。

## 许可证

详见仓库中的许可证信息。
