// Package docs 由 swag init -g doc_swag.go -o docs 生成并覆盖。
// 当前为占位：嵌入 swagger.json，以便未运行 swag 时也能编译；运行 swag init 后会被完整 spec 覆盖。
package docs

import (
	_ "embed"
	"github.com/swaggo/swag"
)

//go:embed swagger.json
var doc string

// spec 实现 swag.Swagger，用于占位注册（swag v1.16 要求 Register 传入带 ReadDoc 的接口）
type spec struct{ s string }

func (s *spec) ReadDoc() string { return s.s }

func init() {
	// 使用 "swagger" 与 swag.ReadDoc() 默认查找的实例名一致，否则 ReadDoc() 返回空导致 openapi.json/yaml 为空
	swag.Register("swagger", &spec{s: doc})
}
