# 后端服务结构

- **auth-service**（Python/FastAPI）：负责用户与认证相关能力，包括注册、登录、刷新令牌、JWT、`/api/auth/validate`，以及通过 `/api/auth/authorize` 实现的**集中式 RBAC**。登录、注册、刷新令牌接口的参考实现见 [docs/auth-api.md](../docs/auth-api.md)。路由会使用 `@permission_required("user.read")` 或 `user.write` 标注权限；权限提取脚本会读取这些标注，并由 Kong 统一执行鉴权。
- **core**（Go）：负责业务 API，暴露 `/hello`、`/admin`、`/api/hello`、`/api/admin` 等接口。权限在路由注册时通过 **handleAPI(mux, method, path, []string{"perm"}, handler)** 声明；权限提取脚本会解析这些调用。Go 服务本身不做逐路由鉴权，鉴权由 Kong 统一完成。

## 集中式鉴权（Kong + auth-service）

1. **静态分析**：构建 auth-service 时，镜像构建流程会运行 `scripts/extract_api_permissions.py`，扫描 **core**（Go）和 **auth-service**（Python），并将 `api_permissions.json` 写入镜像。该脚本支持：
   - **Python**：FastAPI 路由（如 `app.get("/path", ...)`）上的 `@permission_required("perm1", "perm2")`。
   - **Go**：路由注册时对 **handleAPI(mux, method, path, []string{"perm"}, handler)** 的调用。例如：`handleAPI(mux, "GET", "/api/hello", []string{"user.read"}, func(...))`。
2. **auth-service** 加载该文件，并暴露 `POST /api/auth/authorize`。不在权限映射表中的路由无需令牌即可访问；其他路由需要有效 JWT，并且用户必须具备对应权限。
3. **Kong** 在 auth 和 core 路由上使用 `rbac-auth` 插件：该插件会调用 auth-service 的 `/api/auth/authorize`；如果返回 200，则继续转发请求。

因此，core 和 auth-service 都不直接执行逐路由鉴权；所有受保护 API 的鉴权都由 Kong 集中处理。

## 管理员账户（初始化）

首次运行时，auth-service 会根据环境变量创建内置管理员用户：

- **用户名**：`BOOTSTRAP_ADMIN_USERNAME`（docker-compose 中的默认值为 **admin**）
- **密码**：`BOOTSTRAP_ADMIN_PASSWORD`（docker-compose 中的默认值为 **admin**）

因此，使用仓库中的 `docker-compose.yml` 启动时，默认管理员登录信息为 **admin / admin**。

如果你是从旧版本升级而来，旧版本可能使用 `users.role`（字符串）字段；应用会在启动时将其迁移为 `role_id`。如果登录或注册仍然失败，可以删除数据库卷并重新启动：`docker compose down -v && docker compose up -d --build`。

## 部署

1. 构建并运行：`docker compose up --build`。构建 auth-service 时会运行权限提取脚本，将 core Go 服务与 auth-service Python 服务中的权限声明提取为镜像内的 `api_permissions.json`。

2. 可选：本地运行权限提取脚本：`python3 backend/scripts/extract_api_permissions.py --output backend/auth-service/api_permissions.json --exclude scripts,core,vendor backend/core backend/auth-service`。生成的文件已加入 `.gitignore`，不会被提交到仓库。

3. Kong：如果遇到 `module 'resty.http' not found`，请构建自定义 Kong 镜像：在 `docker-compose.yml` 中将 `image: kong:3.6` 改为 `build: ./kong`，并移除 rbac-auth 的 volume 挂载。

## 独立部署

- **auth-service**：需要数据库以及 `JWT_SECRET`、`BOOTSTRAP_ADMIN_USERNAME`、`BOOTSTRAP_ADMIN_PASSWORD` 等环境变量。可选配置：`AUTH_API_PERMISSIONS_FILE`，用于指定 API 与权限的映射文件。
- **core**：无需认证相关环境变量；Kong 或其他网关会调用 auth-service 执行 RBAC 鉴权。

Kong 会将 `/api/auth` 路由到 auth-service，将 `/api` 路由到 core；两类路由都通过 rbac-auth 插件实现集中式 RBAC。
