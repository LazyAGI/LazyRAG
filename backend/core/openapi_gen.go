package main

import (
	"encoding/json"
	"strings"

	"github.com/gorilla/mux"
)

const (
	openAPITitle       = "Backend Core API"
	openAPIVersion     = "0.1.0"
	openAPIDescription = "LazyRAG Go backend core API - proxies to algorithm services. 经 Kong 暴露时前缀为 /api/core。"
	apiPrefix          = "/api/core"
)

// buildOpenAPISpecFromRouter 遍历已注册的路由，生成 OpenAPI 3.0 spec（启动时自动收集，无需手维护 doc_swag.go）
func buildOpenAPISpecFromRouter(r *mux.Router) ([]byte, error) {
	// path -> method -> operation
	type op struct {
		Summary string `json:"summary"`
	}
	pathOps := map[string]map[string]op{}

	err := r.Walk(func(route *mux.Route, _ *mux.Router, _ []*mux.Route) error {
		path, err := route.GetPathTemplate()
		if err != nil || path == "" {
			return nil
		}
		// 文档自身端点不入 spec
		if strings.HasPrefix(path, "/openapi") || path == "/docs" {
			return nil
		}
		methods, err := route.GetMethods()
		if err != nil {
			return nil
		}
		if pathOps[path] == nil {
			pathOps[path] = make(map[string]op)
		}
		for _, m := range methods {
			// OpenAPI 3.0 要求方法名小写（get/post/...），否则 Swagger UI 不会识别为 operation
			lower := strings.ToLower(m)
			pathOps[path][lower] = op{Summary: m + " " + path}
		}
		return nil
	})
	if err != nil {
		return nil, err
	}

	paths := make(map[string]interface{})
	for path, methods := range pathOps {
		// 对外暴露的 URL 统一带上 /api/core 前缀，方便在 Swagger 中直接看到完整路径
		fullPath := apiPrefix + path
		pathItem := make(map[string]interface{})
		for method, op := range methods {
			pathItem[method] = map[string]interface{}{
				"summary":   op.Summary,
				"responses": map[string]interface{}{"200": map[string]string{"description": "OK"}},
			}
		}
		paths[fullPath] = pathItem
	}

	spec := map[string]interface{}{
		"openapi": "3.0.3",
		"info": map[string]interface{}{
			"title":       openAPITitle,
			"version":     openAPIVersion,
			"description": openAPIDescription,
		},
		// server 使用根路径（与浏览器当前 host 保持一致），真正的前缀体现在 paths 的 key 里
		"servers": []map[string]interface{}{
			{"url": "/", "description": "same origin; see paths with /api/core prefix"},
		},
		"paths": paths,
	}
	return json.MarshalIndent(spec, "", "  ")
}

