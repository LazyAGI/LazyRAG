# Core OpenAPI 自动生成方案

本文说明 `core` 服务当前采用的 OpenAPI 生成方案：

- `Operation Registry + Reflect Schema Generator`
- 保留少量 manual override 处理复杂场景

## 背景

`core` 服务使用 `Go + net/http + gorilla/mux`，路由注册集中在 `routes.go`，但历史上 OpenAPI 的 query/body/response 主要依赖 `openapi_manual.go` 手工维护，容易出现：

- 路由已改，文档未更新
- query 参数散落在 handler 中，难以自动收集
- request/response 类型已经存在于 Go 代码中，但没有被统一作为接口契约使用

## 目标

在不重写所有 handler 的前提下，实现：

1. 文档自动覆盖真实路由
2. 常规 JSON 接口尽量从 Go 类型自动生成 schema
3. 减少 `openapi_manual.go` 的维护压力
4. 保留复杂接口的手工兜底能力

## 方案组成

### 1. 路由层

真实路由仍由 `routes.go` 注册。

### 2. Operation Registry

`openapi_registry.go` 中维护核心接口的 `openAPIOperation` 列表，声明：

- `Method`
- `Path`
- `Summary`
- `Tags`
- `PathParams`
- `QueryParams`
- `Headers`
- `RequestBody`
- `Responses`

### 3. Reflect Schema Generator

通过反射读取 Go struct：

- 基本类型映射到 OpenAPI primitive
- struct 递归生成 object schema
- slice/array 生成 array schema
- map 生成 object/additionalProperties schema
- `time.Time` 映射为 `string(date-time)`
- `json` tag 决定字段名
- `omitempty` 和指针/切片/map 等推断字段可选性

### 4. Manual Override

`openapi_manual.go` 继续作为补丁层，处理：

- `multipart/form-data`
- `application/octet-stream`
- `text/event-stream`
- ACL 包装响应
- 动态结构
- 还未迁移到 registry 的 legacy 接口

## 最终拼装逻辑

`openapi_gen.go` 中的生成顺序：

1. 加载基础 swagger 文档
2. merge manual spec
3. overlay registry spec
4. 遍历真实 router，补齐漏掉的 path/method 和 path params
5. 输出最终 OpenAPI

其中：

- `mergeOpenAPISpec`：用于保留 manual/base 中已有内容
- `overlayOpenAPISpec`：用于让 registry 对相同 path/method 的内容优先覆盖 manual 定义

## 为什么不是纯自动

这个方案已经尽量自动化，但它不是完全零声明的全自动方案。原因是 OpenAPI 除了字段类型，还包含很多 Go 类型本身表达不出来的信息，例如：

- 参数位置（path/query/header/body）
- content-type
- 错误响应
- SSE / binary / multipart
- 默认值、枚举、示例、复杂校验约束

因此推荐的实践是：

- 简单 JSON 接口：使用 registry + Go struct 自动生成
- 复杂接口：保留 manual override

## 如何新增一个接口

### 常规 JSON 接口

1. 在 `routes.go` 中注册真实路由
2. 在 `openapi_registry.go` 中新增对应 `openAPIOperation`
3. 如有 query/path 参数，为其定义独立 struct，并通过 tag 标记：
   - `path:"dataset"`
   - `query:"page_size"`
4. 请求体和响应体优先复用已有导出的 Go struct
5. 重启服务后检查导出的 `openapi.json/openapi.yml`

### 复杂接口

如果接口属于上传、下载、SSE、ACL 包装等复杂场景，优先在 `openapi_manual.go` 增加或保留对应 override。

## 推荐约束

为了让自动生成更准确，后续新增接口建议遵守以下约束：

1. query/path 参数尽量使用独立 struct 声明，不要只在 handler 中散读
2. request/response 尽量使用导出的命名 struct
3. 特殊 content-type 必须显式声明
4. 错误响应统一建模
5. 动态 map/外部透传结构使用 manual override

## 当前收益

相较于纯手工维护 `openapi_manual.go`，该方案的收益是：

- 真实路由不容易漏文档
- 常规 JSON 接口可以直接复用 Go 类型
- 前端使用的 `openapi.yml` 更稳定
- 文档维护逐步从“手写 schema”转向“声明接口契约”

## 后续演进建议

后续可以继续推进：

1. 将更多 legacy 接口从 `openapi_manual.go` 迁移到 `openapi_registry.go`
2. 为字段增加更丰富的 tag（如 required、enum、minimum、maximum）
3. 统一错误响应模型
4. 将 registry 从“核心接口覆盖”逐步演进到“所有常规接口覆盖”
