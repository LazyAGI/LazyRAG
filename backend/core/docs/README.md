# OpenAPI 文档生成

本目录下的 `docs.go` 与 `swagger.json` 仍用于提供 `/openapi.json`、`/openapi.yaml` 和 `/docs` 的基础文档资源，但 `core` 的主生成链路已经升级为：

1. 运行时遍历真实注册路由，保证文档不会漏接口；
2. 通过 `openapi_registry.go` 中的 `Operation Registry` 为核心接口声明 path/query/body/response 元数据；
3. 基于 Go struct 反射生成 `components.schemas`；
4. 对 multipart、binary、SSE、ACL 包装等复杂场景继续保留手工 override。

## 当前行为

- `backend/core/openapi_gen.go`：负责拼装最终 OpenAPI 规范。
- `backend/core/openapi_registry.go`：负责新的 Operation Registry 和反射 schema 生成。
- `backend/core/openapi_manual.go`：保留 legacy/manual schema 与复杂接口兜底定义。
- 服务启动后会自动导出：
  - `backend/core/openapi.json`
  - `backend/core/swagger.json`
  - `api/backend/core/swagger.json`
  - `api/backend/core/openapi.yml`

## 新增/修改接口时推荐做法

### 常规 JSON 接口

优先在 `openapi_registry.go` 中新增或更新对应的 `openAPIOperation`：

- `Method`
- `Path`
- `Summary`
- `PathParams`
- `QueryParams`
- `RequestBody`
- `Responses`

并尽量让请求/响应使用导出的 Go struct，以便自动反射生成 schema。

### 复杂接口

以下场景仍建议保留在 `openapi_manual.go` 中做 override：

- `multipart/form-data`
- `application/octet-stream`
- `text/event-stream`
- ACL 包装响应
- 动态 map / 外部服务不稳定返回结构

## 设计原则

- 路由真相源：`routes.go`
- 接口契约真相源：`openapi_registry.go`
- 复杂场景补丁层：`openapi_manual.go`

这样可以减少纯手写 YAML/JSON 的维护成本，同时避免只靠 handler 代码推断导致的参数不准确。
