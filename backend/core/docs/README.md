# OpenAPI 文档生成 (swaggo)

本目录下的 `docs.go` 与 `swagger.json` 用于提供 `/openapi.json`、`/openapi.yaml` 和 `/docs` 的 API 文档。

## 当前行为

- **未运行 swag 时**：使用内嵌的 `swagger.json`（与根目录 `openapi.json` 内容一致）作为占位，服务可正常编译运行。
- **运行 swag 后**：`swag init` 会**覆盖**本目录的 `docs.go`、`swagger.json` 并生成 `swagger.yaml`，文档将完全由 `doc_swag.go` 中的注解驱动，与路由保持一致。

## 更新文档（与 routes 同步）

在 **backend/core** 目录下执行：

```bash
# 安装 swag CLI（仅需一次）
go install github.com/swaggo/swag/cmd/swag@latest

# 根据 doc_swag.go 注解生成 docs
swag init -g doc_swag.go -o docs --parseDependency --parseInternal
```

生成后重新编译并启动 core，`/api/core/docs`、`/api/core/openapi.json`、`/api/core/openapi.yaml` 会使用新 spec。

## 新增/修改接口后

1. 在 `doc_swag.go` 中为对应 path 增加或修改一个带 `@Summary`、`@Router` 等注解的占位函数。
2. 执行上述 `swag init` 命令。
3. 重新构建并部署 core。
