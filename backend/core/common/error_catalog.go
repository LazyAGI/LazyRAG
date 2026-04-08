package common

import (
	"net/http"
	"strings"
)

type AppError struct {
	HTTPStatus int
	Code       int
	Message    string
	Detail     any
}

func NewAppError(httpStatus, code int, message string) *AppError {
	return &AppError{HTTPStatus: httpStatus, Code: code, Message: message}
}

func (e *AppError) WithDetail(detail any) *AppError {
	dup := *e
	dup.Detail = detail
	return &dup
}

func (e *AppError) Error() string {
	return e.Message
}

var errorCatalog = map[string]*AppError{
	"invalid body":                      NewAppError(http.StatusBadRequest, 2000201, "Invalid request body"),
	"invalid json":                      NewAppError(http.StatusBadRequest, 2000202, "Invalid JSON body"),
	"invalid request":                   NewAppError(http.StatusBadRequest, 2000203, "Invalid request"),
	"method not allowed":                NewAppError(http.StatusMethodNotAllowed, 2000204, "Method not allowed"),
	"missing x-user-id":                 NewAppError(http.StatusBadRequest, 2000205, "X-User-Id is required"),
	"missing dataset":                   NewAppError(http.StatusBadRequest, 2000206, "Dataset is required"),
	"missing dataset or document":       NewAppError(http.StatusBadRequest, 2000207, "Dataset or document is required"),
	"missing dataset or upload_file_id": NewAppError(http.StatusBadRequest, 2000208, "Dataset or upload_file_id is required"),
	"missing path":                      NewAppError(http.StatusBadRequest, 2000209, "Path is required"),
	"invalid path encoding":             NewAppError(http.StatusBadRequest, 2000210, "Invalid path encoding"),
	"invalid path":                      NewAppError(http.StatusBadRequest, 2000211, "Invalid path"),
	"missing signature":                 NewAppError(http.StatusForbidden, 2000301, "Signature is required"),
	"url expired":                       NewAppError(http.StatusForbidden, 2000302, "Signed URL has expired"),
	"invalid signature":                 NewAppError(http.StatusForbidden, 2000303, "Invalid signature"),
	"document not found":                NewAppError(http.StatusNotFound, 2000401, "Document not found"),
	"document file not found":           NewAppError(http.StatusNotFound, 2000402, "Document file not found"),
	"uploaded file not found":           NewAppError(http.StatusNotFound, 2000403, "Uploaded file not found"),
	"uploaded file path is empty":       NewAppError(http.StatusNotFound, 2000404, "Uploaded file path is empty"),
	"task not found":                    NewAppError(http.StatusNotFound, 2000405, "Task not found"),
	"prompt not found":                  NewAppError(http.StatusNotFound, 2000406, "Prompt not found"),
	"conversation not found":            NewAppError(http.StatusNotFound, 2000407, "Conversation not found"),
	"resource not found":                NewAppError(http.StatusNotFound, 2000408, "Resource not found"),
	"query documents failed":            NewAppError(http.StatusInternalServerError, 2000501, "Failed to query documents"),
	"create document failed":            NewAppError(http.StatusInternalServerError, 2000502, "Failed to create document"),
	"update document failed":            NewAppError(http.StatusInternalServerError, 2000503, "Failed to update document"),
	"search documents failed":           NewAppError(http.StatusInternalServerError, 2000504, "Failed to search documents"),
	"query tasks failed":                NewAppError(http.StatusInternalServerError, 2000505, "Failed to query tasks"),
	"failed to ensure conversation":     NewAppError(http.StatusInternalServerError, 2000506, "Failed to ensure conversation"),
	"store not initialized":             NewAppError(http.StatusInternalServerError, 2000507, "Store is not initialized"),
	"streaming not supported":           NewAppError(http.StatusInternalServerError, 2000508, "Streaming is not supported"),
	"request failed":                    NewAppError(http.StatusInternalServerError, 2000509, "Request failed"),
	"update failed":                     NewAppError(http.StatusInternalServerError, 2000510, "Update failed"),
	"delete failed":                     NewAppError(http.StatusInternalServerError, 2000511, "Delete failed"),
	"list failed":                       NewAppError(http.StatusInternalServerError, 2000512, "List failed"),
	"name too long":                     NewAppError(http.StatusBadRequest, 2000601, "Name is too long"),
	"content too long":                  NewAppError(http.StatusBadRequest, 2000602, "Content is too long"),
	"display_name and content required": NewAppError(http.StatusBadRequest, 2000603, "Display name and content are required"),
	"display_name/content required":     NewAppError(http.StatusBadRequest, 2000604, "Display name or content is required"),
	"invalid prompt name":               NewAppError(http.StatusBadRequest, 2000605, "Invalid prompt name"),
	"prompt existed":                    NewAppError(http.StatusConflict, 2000606, "Prompt already exists"),
	"task_ids is required":              NewAppError(http.StatusBadRequest, 2000607, "task_ids is required"),
	"invalid multipart form":            NewAppError(http.StatusBadRequest, 2000608, "Invalid multipart form"),
	"no files uploaded":                 NewAppError(http.StatusBadRequest, 2000609, "No files uploaded"),
	"no file uploaded":                  NewAppError(http.StatusBadRequest, 2000610, "No file uploaded"),
	"invalid page_token":                NewAppError(http.StatusBadRequest, 2000611, "Invalid page_token"),
	"input required":                    NewAppError(http.StatusBadRequest, 2000612, "Input is required"),
	"query required":                    NewAppError(http.StatusBadRequest, 2000613, "Query is required"),
	"display_name too long":             NewAppError(http.StatusBadRequest, 2000614, "Display name is too long"),
	"conversation_id too long":          NewAppError(http.StatusBadRequest, 2000615, "conversation_id is too long"),
	"external task id is empty":         NewAppError(http.StatusBadRequest, 2000616, "External task id is empty"),
	"task cannot be canceled":           NewAppError(http.StatusConflict, 2000701, "Task cannot be canceled"),
	"job cannot be canceled":            NewAppError(http.StatusConflict, 2000702, "Job cannot be canceled"),

	"missing dataset or task":                                NewAppError(http.StatusBadRequest, 2000212, "Dataset or task is required"),
	"invalid request body":                                   NewAppError(http.StatusBadRequest, 2000213, "Invalid request body"),
	"task_id in body does not match path":                    NewAppError(http.StatusBadRequest, 2000214, "task_id in body does not match path"),
	"filename is required":                                   NewAppError(http.StatusBadRequest, 2000215, "Filename is required"),
	"file_size must be >= 0":                                 NewAppError(http.StatusBadRequest, 2000216, "file_size must be >= 0"),
	"part_size must be >= 0":                                 NewAppError(http.StatusBadRequest, 2000217, "part_size must be >= 0"),
	"items is required":                                      NewAppError(http.StatusBadRequest, 2000218, "Items are required"),
	"task can only be resumed from failed or canceled state": NewAppError(http.StatusBadRequest, 2000219, "Task can only be resumed from FAILED or CANCELED state"),
	"save upload file failed":                                NewAppError(http.StatusInternalServerError, 2000513, "Failed to save upload file"),
	"create temp dir failed":                                 NewAppError(http.StatusInternalServerError, 2000514, "Failed to create temp dir"),
	"open upload file failed":                                NewAppError(http.StatusBadRequest, 2000220, "Failed to open upload file"),
	"create upload target failed":                            NewAppError(http.StatusInternalServerError, 2000515, "Failed to create upload target"),
	"create uploaded file failed":                            NewAppError(http.StatusInternalServerError, 2000516, "Failed to create uploaded file"),
	"load upload meta failed":                                NewAppError(http.StatusInternalServerError, 2000517, "Failed to load upload meta"),
	"create part failed":                                     NewAppError(http.StatusInternalServerError, 2000518, "Failed to create upload part"),
	"write part failed":                                      NewAppError(http.StatusInternalServerError, 2000519, "Failed to write upload part"),
	"segment not found":                                      NewAppError(http.StatusNotFound, 2000410, "Segment not found"),
	"missing segment":                                        NewAppError(http.StatusBadRequest, 2000221, "Segment is required"),
	"read body failed":                                       NewAppError(http.StatusBadRequest, 2000222, "Failed to read request body"),
	"invalid search_config (top_k 1-10, confidence 0-1)":     NewAppError(http.StatusBadRequest, 2000223, "Invalid search_config"),
	"conversation_id required":                               NewAppError(http.StatusBadRequest, 2000224, "conversation_id is required"),
	"member not found":                                       NewAppError(http.StatusNotFound, 2000411, "Member not found"),
	"invalid role":                                           NewAppError(http.StatusBadRequest, 2000225, "Invalid role"),
	"acl store not initialized":                              NewAppError(http.StatusInternalServerError, 2000520, "ACL store is not initialized"),
	"user_id_list and group_id_list cannot both be empty":    NewAppError(http.StatusBadRequest, 2000226, "user_id_list and group_id_list cannot both be empty"),
	"no valid user_id_list or group_id_list provided":        NewAppError(http.StatusBadRequest, 2000227, "No valid user_id_list or group_id_list provided"),
	"failed to add dataset members":                          NewAppError(http.StatusInternalServerError, 2000521, "Failed to add dataset members"),
	"algo service unavailable":                               NewAppError(http.StatusBadGateway, 2000710, "Algo service is unavailable"),
	"query datasets failed":                                  NewAppError(http.StatusInternalServerError, 2000522, "Failed to query datasets"),
	"algo service error":                                     NewAppError(http.StatusBadGateway, 2000711, "Algo service returned an error"),
}

func ResolveAppError(message string, statusCode int) *AppError {
	base, detail := splitErrorMessage(message)
	if appErr, ok := errorCatalog[normalizeErrorKey(base)]; ok {
		if detail != "" {
			return appErr.WithDetail(detail)
		}
		return appErr
	}
	appErr := &AppError{HTTPStatus: statusCode, Code: ErrorCodeFromHTTPStatus(statusCode), Message: strings.TrimSpace(base)}
	if detail != "" {
		appErr.Detail = detail
	}
	return appErr
}

func splitErrorMessage(message string) (string, string) {
	msg := strings.TrimSpace(message)
	if msg == "" {
		return "unknown error", ""
	}
	if idx := strings.Index(msg, ": "); idx > 0 {
		return strings.TrimSpace(msg[:idx]), strings.TrimSpace(msg[idx+2:])
	}
	return msg, ""
}

func normalizeErrorKey(message string) string {
	return strings.ToLower(strings.TrimSpace(message))
}
