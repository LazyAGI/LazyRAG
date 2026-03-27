// Package docs 嵌入仓库内维护的 OpenAPI JSON 文档。
package docs

import _ "embed"

//go:embed swagger.json
var doc string

// SwaggerDoc 返回当前嵌入的 OpenAPI JSON 文档。
func SwaggerDoc() string { return doc }
