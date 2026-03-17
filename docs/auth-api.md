# LazyRAG 登录、注册与 Token 接口说明

LazyRAG 的**登录、注册、刷新 token** 等认证能力以 **backend/auth-service** 为参考实现，前端、Kong、其他后端服务对接时请以本文及 auth-service 代码为准。

实现位置：`backend/auth-service/api/auth.py`、`services/auth_service.py`、`core/security.py`、`core/rate_limit.py`、`core/redis_client.py`。

**与 LazyCraft / HTTPS 的对接说明**：注册与登录的**校验维度**（用户名格式、密码强度、确认密码、用户名唯一、登录失败限流、Token 颁发与 refresh）已与 LazyCraft 对齐；LazyRAG 不实现 ECDH/请求体解密等 HTTPS 相关逻辑，**HTTPS 由网关或反向代理（如 Kong、Nginx）在接入层处理**，auth-service 仅提供明文 HTTP 的认证接口，部署时通过网关开启 HTTPS 即可。

---

## 1. 接口一览（参考 auth-service）

| 能力       | 方法 + 路径              | 说明 |
|------------|--------------------------|------|
| 注册       | `POST /api/auth/register` | 新用户注册，默认角色为 `user` |
| 登录       | `POST /api/auth/login`    | 用户名密码登录，返回 access_token、refresh_token |
| 刷新 Token | `POST /api/auth/refresh`  | 用 refresh_token 换取新的 access_token 与 refresh_token |
| 校验 Token | `POST /api/auth/validate` | 校验当前 Bearer token，返回 sub、role、permissions |
| 当前用户   | `GET /api/auth/me`       | 需 Bearer token，返回当前用户信息与权限 |
| 修改密码   | `POST /api/auth/change_password` | 需 Bearer token |
| 登出       | `POST /api/auth/logout`   | 可选传 refresh_token，服务端使该 refresh_token 失效 |

---

## 2. 请求/响应约定（与 auth-service 一致）

### 2.0 错误码与错误响应格式（参考 neutrino `authservice`）

- **HTTP 状态码**：仍使用标准 HTTP 状态码（400/401/403/404/500 等）。
- **响应体**：统一为：
  - `code`: int（HTTP 状态码）
  - `message`: str（面向用户/调用方的错误信息）
  - `data`: object | null（可选，包含业务错误码等）
    - `data.code`: int（业务错误码，例如 `1000115`）
    - `data.message`: str
    - `data.ex_mesage`: str（可选扩展信息，与 `authservice` 一致）

### 2.1 注册 `POST /api/auth/register`

- **请求体**：`RegisterBody`
  - `username`: str（必填，格式：至少 2 位，字母或数字开头/结尾，中间可含字母数字及 `. _ @ # -`）
  - `password`: str（必填，8～32 位，须含大小写、数字、特殊字符）
  - `confirm_password`: str（必填，须与 `password` 一致）
  - `email`: str | null
  - `tenant_id`: str | null
- **成功响应**：`{ "success": true, "user_id": "<id>", "tenant_id": "<tid>", "role": "user" }`
- **错误**：400（如用户名已存在、密码与确认密码不一致、用户名/密码格式不符合要求；响应体见 2.0）

### 2.2 登录 `POST /api/auth/login`

- **请求体**：`LoginBody`  
  - `username`: str  
  - `password`: str  
- **成功响应**：
  - `access_token`: str（JWT，请求接口时放在 Header `Authorization: Bearer <access_token>`）
  - `refresh_token`: str（用于调用 refresh，建议前端安全存储）
  - `token_type`: `"bearer"`
  - `role`: str
  - `expires_in`: int（秒）
  - `tenant_id`: str | null
- **错误**：401（用户名或密码错误、用户被禁用、**登录失败限流**等）
- **登录失败限流**（与 LazyCraft 对齐）：同一账号在 1 分钟内连续失败 3 次后，将返回 400，`message` 为「登录已锁定，请稍后再试」，`data.code` 为 `1000114`。限流按用户维度、**Redis ZSET 滑动窗口实现**（多实例天然一致）。Redis 连接可通过 `LAZYRAG_REDIS_URL` 配置（未配置时默认 `redis://localhost:6379/0`）。

### 2.3 刷新 Token `POST /api/auth/refresh`

- **请求体**：`RefreshBody`  
  - `refresh_token`: str（必填，即登录返回的 refresh_token）
- **成功响应**：与登录相同结构，返回新的 `access_token`、`refresh_token` 等。
- **错误**：401（refresh_token 缺失、无效或过期）

### 2.4 校验 Token `POST /api/auth/validate`

- **Header**：`Authorization: Bearer <access_token>`
- **成功响应**：`{ "sub": "<user_id>", "role": "<role>", "tenant_id": "<tid>", "permissions": ["perm1", ...] }`
- **错误**：401（无 token 或 token 无效）

### 2.5 当前用户 `GET /api/auth/me`

- **Header**：`Authorization: Bearer <access_token>`
- **成功响应**：`{ "user_id", "username", "email", "status", "role", "permissions", "tenant_id" }`
- **错误**：401

### 2.6 修改密码 `POST /api/auth/change_password`

- **Header**：`Authorization: Bearer <access_token>`
- **请求体**：`old_password`, `new_password`（new_password 至少 8 位）
- **成功响应**：`{ "success": true }`
- **错误**：400（旧密码错误或新密码过短）、401、404

### 2.7 登出 `POST /api/auth/logout`

- **Header**：`Authorization: Bearer <access_token>`
- **请求体**：`refresh_token` 可选；若传入则服务端使该 refresh_token 失效。
- **成功响应**：`{ "success": true }`

---

## 3. 与 neutrino authservice 的参考关系

- **LazyRAG auth-service**：采用 **JWT access_token + refresh_token** 模型，无 OAuth2/Hydra；注册、登录、刷新、校验、登出均在 auth-service 内完成，Kong 通过 `POST /api/auth/authorize` 做统一鉴权。
- **neutrino authservice**：采用 **Hydra OAuth2**（login_challenge、consent、redirect），登录流程与 LazyRAG 不同；用户、密码校验、加密等实现可作参考（如密码强度、错误码约定、repository 分层）。
- 对接 LazyRAG 时，**以本文及 `backend/auth-service` 的接口与行为为准**；若需与 neutrino 行为对齐，可仅在密码策略、错误信息等非接口层面参考 neutrino 实现。

---

## 4. Token 颁发与刷新（与 LazyCraft 机制对齐）

- **登录**：成功登录后颁发 **access_token**（JWT）和 **refresh_token**；access_token 有效期由 `LAZYRAG_JWT_TTL_MINUTES` 控制（默认 60 分钟），refresh_token 有效期由 `LAZYRAG_JWT_REFRESH_TTL_DAYS` 控制（默认 7 天）。
- **刷新**：在 access_token 过期或即将过期时，客户端调用 `POST /api/auth/refresh` 传入 **refresh_token**，服务端校验通过后返回新的 access_token 与 refresh_token；旧 refresh_token 可配置为一次性使用（当前实现为可重复使用至过期）。
- **登出**：客户端调用 `POST /api/auth/logout` 并可选传入当前 refresh_token，服务端使该 refresh_token 失效；前端清除本地 token。

## 5. 认证功能点与 LazyCraft 对齐一览

| 功能点           | LazyCraft | LazyRAG auth-service |
|------------------|-----------|------------------------|
| 用户名格式校验   | ✓         | ✓（2 位起、字母数字及 `. _ @ # -`） |
| 密码强度         | ✓（8～128 位） | ✓（8～32 位，含大小写+数字+特殊字符） |
| 确认密码一致     | ✓         | ✓ |
| 用户名唯一       | ✓         | ✓ |
| 登录失败限流     | ✓（3 次/分钟/账号） | ✓（3 次/分钟/账号，Redis ZSET 实现） |
| Token + refresh  | ✓         | ✓（access_token + refresh_token） |
| HTTPS            | 接入层/网关 | 由网关处理，auth-service 不负责加解密 |

## 6. 前端/Kong 使用建议

1. **登录**：调用 `POST /api/auth/login`，将返回的 `access_token` 存于内存或安全存储，`refresh_token` 安全存储（如 httpOnly cookie 或安全存储）。
2. **请求 API**：在请求头中携带 `Authorization: Bearer <access_token>`。
3. **刷新**：在 access_token 过期前或收到 401 时，用 `POST /api/auth/refresh` 传入 `refresh_token` 获取新 access_token 与 refresh_token，再重试原请求。
4. **登出**：调用 `POST /api/auth/logout`，可选传当前 refresh_token；前端清除本地 token。

以上行为与 `backend/auth-service` 当前实现一致，如有变更以 auth-service 代码为准。
