package server

import "testing"

func TestOpenAPISpecDoesNotExposeInjectedUserHeaders(t *testing.T) {
	spec := buildOpenAPISpec()
	paths, ok := spec["paths"].(map[string]any)
	if !ok {
		t.Fatalf("paths missing in openapi spec")
	}

	pathItem, ok := paths["/api/scan/sources"].(map[string]any)
	if !ok {
		t.Fatalf("path missing from openapi spec: /api/scan/sources")
	}

	for _, method := range []string{"get", "post"} {
		op, ok := pathItem[method].(map[string]any)
		if !ok {
			t.Fatalf("operation missing from openapi spec: %s /api/scan/sources", method)
		}
		params, _ := op["parameters"].([]any)
		for _, item := range params {
			param, ok := item.(map[string]any)
			if !ok {
				continue
			}
			name, _ := param["name"].(string)
			inVal, _ := param["in"].(string)
			if inVal == "header" && (name == "X-User-Id" || name == "X-User-ID" || name == "X-User-Name") {
				t.Fatalf("unexpected injected user header parameter %q on %s /api/scan/sources", name, method)
			}
		}
	}
}
