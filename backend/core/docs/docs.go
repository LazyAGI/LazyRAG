// Package docs text OpenAPI JSON Document。
package docs

import _ "embed"

//go:embed swagger.json
var doc string

// SwaggerDoc text OpenAPI JSON Document。
func SwaggerDoc() string { return doc }
