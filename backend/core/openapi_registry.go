package main

import (
	"fmt"
	"reflect"
	"sort"
	"strings"

	"lazyrag/core/chat"
	"lazyrag/core/doc"
	"lazyrag/core/wordgroup"
)

type schemaSource struct {
	Type   any
	Ref    string
	Inline map[string]any
}

type openAPIBody struct {
	Required    bool
	ContentType string
	Schema      schemaSource
}

type openAPIResponse struct {
	Description string
	ContentType string
	Schema      schemaSource
}

type openAPIOperation struct {
	Method      string
	Path        string
	Summary     string
	Tags        []string
	PathParams  any
	QueryParams any
	Headers     any
	RequestBody *openAPIBody
	Responses   map[int]openAPIResponse
}

type schemaBuilder struct {
	components map[string]any
	seen       map[reflect.Type]string
}

func newSchemaBuilder() *schemaBuilder {
	return &schemaBuilder{
		components: map[string]any{},
		seen:       map[reflect.Type]string{},
	}
}

func operationRegistryOpenAPISpec() map[string]any {
	builder := newSchemaBuilder()
	paths := map[string]any{}
	for _, op := range registeredCoreOperations() {
		pathItem, _ := paths[op.Path].(map[string]any)
		if pathItem == nil {
			pathItem = map[string]any{}
			paths[op.Path] = pathItem
		}
		pathItem[strings.ToLower(op.Method)] = op.toOpenAPI(builder)
	}
	return map[string]any{
		"components": map[string]any{
			"schemas": builder.components,
		},
		"paths": paths,
	}
}

func (op openAPIOperation) toOpenAPI(builder *schemaBuilder) map[string]any {
	result := map[string]any{
		"summary": op.Summary,
	}
	if len(op.Tags) > 0 {
		result["tags"] = op.Tags
	}

	params := make([]map[string]any, 0)
	params = append(params, buildStructParameters(op.PathParams, "path", builder)...)
	params = append(params, buildStructParameters(op.QueryParams, "query", builder)...)
	params = append(params, buildStructParameters(op.Headers, "header", builder)...)
	if len(params) > 0 {
		items := make([]any, 0, len(params))
		for _, item := range params {
			items = append(items, item)
		}
		result["parameters"] = items
	}

	if op.RequestBody != nil {
		contentType := op.RequestBody.ContentType
		if contentType == "" {
			contentType = "application/json"
		}
		result["requestBody"] = map[string]any{
			"required": op.RequestBody.Required,
			"content": map[string]any{
				contentType: map[string]any{
					"schema": builder.schemaFromSource(op.RequestBody.Schema),
				},
			},
		}
	}

	responses := map[string]any{}
	for _, code := range sortedStatusCodes(op.Responses) {
		resp := op.Responses[code]
		description := resp.Description
		if description == "" {
			description = httpStatusText(code)
		}
		contentType := resp.ContentType
		if contentType == "" {
			contentType = "application/json"
		}
		entry := map[string]any{"description": description}
		if schema := builder.schemaFromSource(resp.Schema); schema != nil {
			entry["content"] = map[string]any{
				contentType: map[string]any{"schema": schema},
			}
		}
		responses[fmt.Sprintf("%d", code)] = entry
	}
	if len(responses) == 0 {
		responses["200"] = map[string]any{"description": "OK"}
	}
	result["responses"] = responses
	return result
}

func buildStructParameters(v any, location string, builder *schemaBuilder) []map[string]any {
	if v == nil {
		return nil
	}
	t := reflect.TypeOf(v)
	for t.Kind() == reflect.Pointer {
		t = t.Elem()
	}
	if t.Kind() != reflect.Struct {
		return nil
	}
	params := make([]map[string]any, 0)
	for i := 0; i < t.NumField(); i++ {
		field := t.Field(i)
		if !field.IsExported() {
			continue
		}
		name, ok := field.Tag.Lookup(location)
		if !ok || strings.TrimSpace(name) == "" || name == "-" {
			continue
		}
		schema := builder.schemaForType(field.Type)
		if schema == nil {
			continue
		}
		required := location == "path" || field.Tag.Get("required") == "true"
		params = append(params, map[string]any{
			"name":     name,
			"in":       location,
			"required": required,
			"schema":   schema,
		})
	}
	return params
}

func (b *schemaBuilder) schemaFromSource(source schemaSource) map[string]any {
	if source.Inline != nil {
		return source.Inline
	}
	if source.Ref != "" {
		return refSchema(source.Ref)
	}
	if source.Type == nil {
		return nil
	}
	return b.schemaForType(reflect.TypeOf(source.Type))
}

func (b *schemaBuilder) schemaForType(t reflect.Type) map[string]any {
	if t == nil {
		return nil
	}
	for t.Kind() == reflect.Pointer {
		t = t.Elem()
	}
	if schema := inlineSpecialSchema(t); schema != nil {
		return schema
	}
	if isPrimitiveKind(t.Kind()) || t.Kind() == reflect.Slice || t.Kind() == reflect.Array || t.Kind() == reflect.Map || t.Kind() == reflect.Interface {
		return b.inlineSchemaForType(t)
	}
	if t.Kind() == reflect.Struct {
		name := schemaNameForType(t)
		if existing, ok := b.seen[t]; ok {
			return refSchema(existing)
		}
		b.seen[t] = name
		b.components[name] = b.inlineSchemaForType(t)
		return refSchema(name)
	}
	return map[string]any{"type": "string"}
}

func (b *schemaBuilder) inlineSchemaForType(t reflect.Type) map[string]any {
	if t == nil {
		return nil
	}
	for t.Kind() == reflect.Pointer {
		t = t.Elem()
	}
	if schema := inlineSpecialSchema(t); schema != nil {
		return schema
	}
	switch t.Kind() {
	case reflect.String:
		return map[string]any{"type": "string"}
	case reflect.Bool:
		return map[string]any{"type": "boolean"}
	case reflect.Int, reflect.Int8, reflect.Int16, reflect.Int32, reflect.Int64:
		schema := map[string]any{"type": "integer"}
		if t.Kind() == reflect.Int64 {
			schema["format"] = "int64"
		}
		return schema
	case reflect.Uint, reflect.Uint8, reflect.Uint16, reflect.Uint32, reflect.Uint64:
		schema := map[string]any{"type": "integer", "minimum": 0}
		if t.Kind() == reflect.Uint64 {
			schema["format"] = "int64"
		}
		return schema
	case reflect.Float32:
		return map[string]any{"type": "number", "format": "float"}
	case reflect.Float64:
		return map[string]any{"type": "number", "format": "double"}
	case reflect.Slice, reflect.Array:
		return map[string]any{"type": "array", "items": b.schemaForType(t.Elem())}
	case reflect.Map:
		if t.Key().Kind() != reflect.String {
			return obj()
		}
		return map[string]any{"type": "object", "additionalProperties": b.schemaForType(t.Elem())}
	case reflect.Interface:
		return obj()
	case reflect.Struct:
		properties := map[string]any{}
		required := make([]string, 0)
		for i := 0; i < t.NumField(); i++ {
			field := t.Field(i)
			if !field.IsExported() {
				continue
			}
			name, omitEmpty, skip := jsonFieldName(field)
			if skip {
				continue
			}
			properties[name] = b.schemaForType(field.Type)
			if field.Tag.Get("required") == "true" || (!omitEmpty && !isOptionalField(field.Type)) {
				required = append(required, name)
			}
		}
		sort.Strings(required)
		result := map[string]any{"type": "object", "properties": properties}
		if len(required) > 0 {
			result["required"] = required
		}
		return result
	default:
		return map[string]any{"type": "string"}
	}
}

func inlineSpecialSchema(t reflect.Type) map[string]any {
	if t.PkgPath() == "time" && t.Name() == "Time" {
		return map[string]any{"type": "string", "format": "date-time"}
	}
	return nil
}

func jsonFieldName(field reflect.StructField) (name string, omitEmpty bool, skip bool) {
	jsonTag := field.Tag.Get("json")
	if jsonTag == "-" {
		return "", false, true
	}
	if jsonTag == "" {
		return lowerCamel(field.Name), false, false
	}
	parts := strings.Split(jsonTag, ",")
	name = strings.TrimSpace(parts[0])
	if name == "" {
		name = lowerCamel(field.Name)
	}
	for _, part := range parts[1:] {
		if strings.TrimSpace(part) == "omitempty" {
			omitEmpty = true
		}
	}
	return name, omitEmpty, false
}

func lowerCamel(v string) string {
	if v == "" {
		return v
	}
	return strings.ToLower(v[:1]) + v[1:]
}

func isOptionalField(t reflect.Type) bool {
	for t.Kind() == reflect.Pointer {
		return true
	}
	switch t.Kind() {
	case reflect.Map, reflect.Slice, reflect.Interface:
		return true
	default:
		return false
	}
}

func isPrimitiveKind(kind reflect.Kind) bool {
	switch kind {
	case reflect.String, reflect.Bool,
		reflect.Int, reflect.Int8, reflect.Int16, reflect.Int32, reflect.Int64,
		reflect.Uint, reflect.Uint8, reflect.Uint16, reflect.Uint32, reflect.Uint64,
		reflect.Float32, reflect.Float64:
		return true
	default:
		return false
	}
}

func schemaNameForType(t reflect.Type) string {
	if name := t.Name(); name != "" {
		return name
	}
	return strings.ReplaceAll(t.String(), ".", "_")
}

func sortedStatusCodes(responses map[int]openAPIResponse) []int {
	codes := make([]int, 0, len(responses))
	for code := range responses {
		codes = append(codes, code)
	}
	sort.Ints(codes)
	return codes
}

func httpStatusText(code int) string {
	switch code {
	case 200:
		return "OK"
	case 201:
		return "Created"
	case 204:
		return "No Content"
	case 400:
		return "Bad Request"
	case 401:
		return "Unauthorized"
	case 403:
		return "Forbidden"
	case 404:
		return "Not Found"
	case 500:
		return "Internal Server Error"
	default:
		return "Response"
	}
}

type datasetPathParams struct {
	Dataset string `path:"dataset"`
}

type documentPathParams struct {
	Dataset  string `path:"dataset"`
	Document string `path:"document"`
}

type taskPathParams struct {
	Dataset string `path:"dataset"`
	Task    string `path:"task"`
}

type uploadPathParams struct {
	Dataset  string `path:"dataset"`
	UploadID string `path:"upload_id"`
}

type exportConversationFilePathParams struct {
	FileID string `path:"file_id"`
}

type datasetQueryParams struct {
	PageToken string   `query:"page_token"`
	PageSize  int32    `query:"page_size"`
	OrderBy   string   `query:"order_by"`
	Keyword   string   `query:"keyword"`
	Tags      []string `query:"tags"`
}

type createDatasetQueryParams struct {
	DatasetID string `query:"dataset_id"`
}

type listDocumentsQueryParams struct {
	PageToken string `query:"page_token"`
	PageSize  int32  `query:"page_size"`
}

type listTasksQueryParams struct {
	PageToken   string `query:"page_token"`
	PageSize    int32  `query:"page_size"`
	TaskState   string `query:"task_state"`
	TaskType    string `query:"task_type"`
	DocumentID  string `query:"document_id"`
	DocumentPID string `query:"document_pid"`
}

func registeredCoreOperations() []openAPIOperation {
	jsonBodyOf := func(v any, required bool) *openAPIBody {
		return &openAPIBody{Required: required, ContentType: "application/json", Schema: schemaSource{Type: v}}
	}
	resp := func(description string, v any) openAPIResponse {
		return openAPIResponse{Description: description, ContentType: "application/json", Schema: schemaSource{Type: v}}
	}
	refResp := func(description, name string) openAPIResponse {
		return openAPIResponse{Description: description, ContentType: "application/json", Schema: schemaSource{Ref: name}}
	}
	return []openAPIOperation{
		{
			Method:      "GET",
			Path:        "/datasets",
			Summary:     "Dataset list",
			Tags:        []string{"datasets"},
			QueryParams: datasetQueryParams{},
			Responses:   map[int]openAPIResponse{200: resp("Dataset list", doc.ListDatasetsResponse{})},
		},
		{
			Method:      "POST",
			Path:        "/datasets",
			Summary:     "Create dataset",
			Tags:        []string{"datasets"},
			QueryParams: createDatasetQueryParams{},
			RequestBody: jsonBodyOf(doc.Dataset{}, false),
			Responses:   map[int]openAPIResponse{200: resp("Created dataset", doc.Dataset{})},
		},
		{
			Method:     "GET",
			Path:       "/datasets/{dataset}",
			Summary:    "Get dataset",
			Tags:       []string{"datasets"},
			PathParams: datasetPathParams{},
			Responses:  map[int]openAPIResponse{200: resp("Dataset details", doc.Dataset{})},
		},
		{
			Method:      "PATCH",
			Path:        "/datasets/{dataset}",
			Summary:     "Update dataset",
			Tags:        []string{"datasets"},
			PathParams:  datasetPathParams{},
			RequestBody: jsonBodyOf(doc.Dataset{}, false),
			Responses:   map[int]openAPIResponse{200: resp("Updated dataset", doc.Dataset{})},
		},
		{
			Method:     "DELETE",
			Path:       "/datasets/{dataset}",
			Summary:    "Delete dataset",
			Tags:       []string{"datasets"},
			PathParams: datasetPathParams{},
			Responses:  map[int]openAPIResponse{200: refResp("Deleted successfully", "EmptyObject")},
		},
		{
			Method:      "POST",
			Path:        "/datasets/{dataset}:setDefault",
			Summary:     "Set as default dataset",
			Tags:        []string{"datasets"},
			PathParams:  datasetPathParams{},
			RequestBody: jsonBodyOf(doc.SetDefaultDatasetRequest{}, true),
			Responses:   map[int]openAPIResponse{200: refResp("Set successfully", "EmptyObject")},
		},
		{
			Method:      "POST",
			Path:        "/datasets/{dataset}:unsetDefault",
			Summary:     "Unset default dataset",
			Tags:        []string{"datasets"},
			PathParams:  datasetPathParams{},
			RequestBody: jsonBodyOf(doc.UnsetDefaultDatasetRequest{}, true),
			Responses:   map[int]openAPIResponse{200: refResp("Unset successfully", "EmptyObject")},
		},
		{
			Method:      "GET",
			Path:        "/datasets/{dataset}/documents",
			Summary:     "Document list",
			Tags:        []string{"documents"},
			PathParams:  datasetPathParams{},
			QueryParams: listDocumentsQueryParams{},
			Responses:   map[int]openAPIResponse{200: resp("Document list", doc.ListDocumentsResponse{})},
		},
		{
			Method:      "POST",
			Path:        "/datasets/{dataset}/documents",
			Summary:     "Create document",
			Tags:        []string{"documents"},
			PathParams:  datasetPathParams{},
			RequestBody: jsonBodyOf(doc.Doc{}, false),
			Responses:   map[int]openAPIResponse{200: resp("Created document", doc.Doc{})},
		},
		{
			Method:     "GET",
			Path:       "/datasets/{dataset}/documents/{document}",
			Summary:    "Get document",
			Tags:       []string{"documents"},
			PathParams: documentPathParams{},
			Responses:  map[int]openAPIResponse{200: resp("Document details", doc.Doc{})},
		},
		{
			Method:      "PATCH",
			Path:        "/datasets/{dataset}/documents/{document}",
			Summary:     "Update document",
			Tags:        []string{"documents"},
			PathParams:  documentPathParams{},
			RequestBody: jsonBodyOf(doc.Doc{}, false),
			Responses:   map[int]openAPIResponse{200: resp("Updated document", doc.Doc{})},
		},
		{
			Method:     "DELETE",
			Path:       "/datasets/{dataset}/documents/{document}",
			Summary:    "Delete document",
			Tags:       []string{"documents"},
			PathParams: documentPathParams{},
			Responses:  map[int]openAPIResponse{200: refResp("Deleted successfully", "EmptyObject")},
		},
		{
			Method:      "POST",
			Path:        "/datasets/{dataset}/documents:search",
			Summary:     "Search documents",
			Tags:        []string{"documents"},
			PathParams:  datasetPathParams{},
			RequestBody: jsonBodyOf(doc.SearchDocumentsRequest{}, false),
			Responses:   map[int]openAPIResponse{200: resp("Document search results", doc.ListDocumentsResponse{})},
		},
		{
			Method:      "POST",
			Path:        "/documents:search",
			Summary:     "textSearch documents",
			Tags:        []string{"documents"},
			RequestBody: jsonBodyOf(doc.SearchDocumentsRequest{}, false),
			Responses:   map[int]openAPIResponse{200: resp("textDocument search results", doc.ListDocumentsResponse{})},
		},
		{
			Method:      "POST",
			Path:        "/datasets/{dataset}:batchDelete",
			Summary:     "BatchDelete document",
			Tags:        []string{"documents"},
			PathParams:  datasetPathParams{},
			RequestBody: jsonBodyOf(doc.BatchDeleteDocumentRequest{}, true),
			Responses:   map[int]openAPIResponse{200: refResp("Deleted successfully", "EmptyObject")},
		},
		{
			Method:      "GET",
			Path:        "/datasets/{dataset}/tasks",
			Summary:     "Task list",
			Tags:        []string{"tasks"},
			PathParams:  datasetPathParams{},
			QueryParams: listTasksQueryParams{},
			Responses:   map[int]openAPIResponse{200: resp("Task list", doc.ListTasksResponse{})},
		},
		{
			Method:      "POST",
			Path:        "/datasets/{dataset}/tasks",
			Summary:     "Create task",
			Tags:        []string{"tasks"},
			PathParams:  datasetPathParams{},
			RequestBody: jsonBodyOf(doc.CreateTaskRequest{}, true),
			Responses:   map[int]openAPIResponse{200: resp("Created task", doc.CreateTasksResponse{})},
		},
		{
			Method:      "POST",
			Path:        "/datasets/{dataset}/tasks:search",
			Summary:     "Search tasks by task ID",
			Tags:        []string{"tasks"},
			PathParams:  datasetPathParams{},
			RequestBody: jsonBodyOf(doc.SearchTasksRequest{}, true),
			Responses:   map[int]openAPIResponse{200: resp("Task search results", doc.ListTasksResponse{})},
		},
		{
			Method:     "GET",
			Path:       "/datasets/{dataset}/tasks/{task}",
			Summary:    "Get task",
			Tags:       []string{"tasks"},
			PathParams: taskPathParams{},
			Responses:  map[int]openAPIResponse{200: resp("Task details", doc.TaskResponse{})},
		},
		{
			Method:     "DELETE",
			Path:       "/datasets/{dataset}/tasks/{task}",
			Summary:    "Delete task",
			Tags:       []string{"tasks"},
			PathParams: taskPathParams{},
			Responses:  map[int]openAPIResponse{200: refResp("Deleted successfully", "EmptyObject")},
		},
		{
			Method:      "POST",
			Path:        "/datasets/{dataset}/tasks:start",
			Summary:     "Start task",
			Tags:        []string{"tasks"},
			PathParams:  datasetPathParams{},
			RequestBody: jsonBodyOf(doc.StartTaskRequest{}, true),
			Responses:   map[int]openAPIResponse{200: resp("Start result", doc.StartTasksResponse{})},
		},
		{
			Method:      "POST",
			Path:        "/datasets/{dataset}/tasks/{task}:resume",
			Summary:     "Resume task",
			Tags:        []string{"tasks"},
			PathParams:  taskPathParams{},
			RequestBody: jsonBodyOf(doc.ResumeTaskRequest{}, false),
			Responses:   map[int]openAPIResponse{200: resp("Resume result", doc.StartTasksResponse{})},
		},
		{
			Method:      "POST",
			Path:        "/datasets/{dataset}/tasks/{task}:suspend",
			Summary:     "Suspend task",
			Tags:        []string{"tasks"},
			PathParams:  taskPathParams{},
			RequestBody: jsonBodyOf(doc.SuspendJobRequest{}, true),
			Responses:   map[int]openAPIResponse{200: refResp("Suspended successfully", "EmptyObject")},
		},
		{
			Method:      "POST",
			Path:        "/datasets/{dataset}/uploads:initUpload",
			Summary:     "Initialize dataset upload",
			Tags:        []string{"tasks"},
			PathParams:  datasetPathParams{},
			RequestBody: jsonBodyOf(doc.InitUploadRequest{}, true),
			Responses:   map[int]openAPIResponse{200: resp("Upload initialization result", doc.InitUploadResponse{})},
		},
		{
			Method:  "PUT",
			Path:    "/datasets/{dataset}/uploads/{upload_id}/parts/{part_number}",
			Summary: "UploadDatasettext",
			Tags:    []string{"tasks"},
			PathParams: struct {
				Dataset    string `path:"dataset"`
				UploadID   string `path:"upload_id"`
				PartNumber string `path:"part_number"`
			}{},
			RequestBody: &openAPIBody{Required: true, ContentType: "application/octet-stream", Schema: schemaSource{Inline: map[string]any{"type": "string", "format": "binary"}}},
			Responses:   map[int]openAPIResponse{200: refResp("Part upload result", "UploadPartResponse")},
		},
		{
			Method:      "POST",
			Path:        "/datasets/{dataset}/uploads/{upload_id}:complete",
			Summary:     "Complete upload",
			Tags:        []string{"tasks"},
			PathParams:  uploadPathParams{},
			RequestBody: jsonBodyOf(doc.CompleteUploadRequest{}, false),
			Responses:   map[int]openAPIResponse{200: resp("Complete uploadtext", doc.CompleteUploadResponse{})},
		},
		{
			Method:      "POST",
			Path:        "/datasets/{dataset}/uploads/{upload_id}:abort",
			Summary:     "Abort upload",
			Tags:        []string{"tasks"},
			PathParams:  uploadPathParams{},
			RequestBody: jsonBodyOf(doc.AbortUploadRequest{}, false),
			Responses:   map[int]openAPIResponse{200: refResp("Abort uploadtext", "AbortUploadResponse")},
		},
		{
			Method:      "POST",
			Path:        "/temp/uploads:initUpload",
			Summary:     "Initialize temp multipart upload",
			Tags:        []string{"uploads"},
			RequestBody: jsonBodyOf(doc.InitUploadRequest{}, true),
			Responses:   map[int]openAPIResponse{200: resp("Upload initialization result", doc.InitUploadResponse{})},
		},
		{
			Method:  "PUT",
			Path:    "/temp/uploads/{upload_id}/parts/{part_number}",
			Summary: "Upload temp filetext",
			Tags:    []string{"uploads"},
			PathParams: struct {
				UploadID   string `path:"upload_id"`
				PartNumber string `path:"part_number"`
			}{},
			RequestBody: &openAPIBody{Required: true, ContentType: "application/octet-stream", Schema: schemaSource{Inline: map[string]any{"type": "string", "format": "binary"}}},
			Responses:   map[int]openAPIResponse{200: refResp("Part upload result", "UploadPartResponse")},
		},
		{
			Method:  "POST",
			Path:    "/temp/uploads/{upload_id}:complete",
			Summary: "textUpload",
			Tags:    []string{"uploads"},
			PathParams: struct {
				UploadID string `path:"upload_id"`
			}{},
			RequestBody: jsonBodyOf(doc.CompleteUploadRequest{}, false),
			Responses:   map[int]openAPIResponse{200: resp("Complete uploadtext", doc.CompleteUploadResponse{})},
		},
		{
			Method:      "POST",
			Path:        "/conversation:export",
			Summary:     "Export conversations",
			Tags:        []string{"conversations"},
			RequestBody: jsonBodyOf(chat.ExportConversationsRequest{}, true),
			Responses:   map[int]openAPIResponse{200: resp("Export conversation files", chat.ExportConversationsResponse{})},
		},
		{
			Method:     "GET",
			Path:       "/conversation:export/files/{file_id}",
			Summary:    "Download exported conversation file",
			Tags:       []string{"conversations"},
			PathParams: exportConversationFilePathParams{},
			Responses:  map[int]openAPIResponse{200: {Description: "Exported conversation file", ContentType: "application/octet-stream", Schema: schemaSource{Inline: map[string]any{"type": "string", "format": "binary"}}}},
		},
		{
			Method:  "POST",
			Path:    "/temp/uploads/{upload_id}:abort",
			Summary: "AborttextUpload",
			Tags:    []string{"uploads"},
			PathParams: struct {
				UploadID string `path:"upload_id"`
			}{},
			RequestBody: jsonBodyOf(doc.AbortUploadRequest{}, false),
			Responses:   map[int]openAPIResponse{200: refResp("Abort uploadtext", "AbortUploadResponse")},
		},
		{
			Method:      "POST",
			Path:        "/word_group:checkExists",
			Summary:     "Check which words already exist",
			Tags:        []string{"word_group"},
			RequestBody: jsonBodyOf(wordgroup.CheckWordsExistRequest{}, true),
			Responses:   map[int]openAPIResponse{200: resp("Existing words among term and aliases", wordgroup.CheckWordsExistResponse{})},
		},
		{
			Method:  "DELETE",
			Path:    "/word_group/{group_id}",
			Summary: "Delete word group by group_id",
			Tags:    []string{"word_group"},
			PathParams: struct {
				GroupID string `path:"group_id"`
			}{},
			Responses: map[int]openAPIResponse{200: resp("Deleted word group", wordgroup.DeleteWordGroupResponse{})},
		},
		{
			Method:      "POST",
			Path:        "/word_group",
			Summary:     "Create word group",
			Tags:        []string{"word_group"},
			RequestBody: jsonBodyOf(wordgroup.CreateWordGroupRequest{}, true),
			Responses:   map[int]openAPIResponse{200: resp("Created word group", wordgroup.CreateWordGroupResponse{})},
		},
	}
}
