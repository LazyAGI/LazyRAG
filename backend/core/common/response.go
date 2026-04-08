package common

import (
	"encoding/json"
	"net/http"
)

// APIResponse text core textResponsetext：{ code, message, data }。
type APIResponse struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
	Data    any    `json:"data,omitempty"`
}

const (
	CodeOK = 0
)

// Core business error codes.
const (
	ErrCodeInternal       = 2000000
	ErrCodeForbidden      = 2000102
	ErrCodeInvalidParams  = 2000103
	ErrCodeUnauthorized   = 2000104
	ErrCodeResourceAbsent = 2000106
	ErrCodeConflict       = 2000107
	ErrCodeRateLimited    = 2000108
	ErrCodeBadGateway     = 2000110
)

func ReplyOK(w http.ResponseWriter, data any) {
	reply(w, CodeOK, "ok", data, http.StatusOK)
}

func ReplyErr(w http.ResponseWriter, message string, statusCode int) {
	reply(w, ErrorCodeFromHTTPStatus(statusCode), message, nil, statusCode)
}

func ReplyErrWithData(w http.ResponseWriter, message string, data any, statusCode int) {
	reply(w, ErrorCodeFromHTTPStatus(statusCode), message, data, statusCode)
}

func reply(w http.ResponseWriter, code int, message string, data any, statusCode int) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(statusCode)
	_ = json.NewEncoder(w).Encode(APIResponse{Code: code, Message: message, Data: data})
}

// ReplyJSON text v text JSON textResponse，Content-Type text application/json。
func ReplyJSON(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(v)
}

// ErrorCodeFromHTTPStatus maps HTTP non-200 codes to core business error codes.
func ErrorCodeFromHTTPStatus(statusCode int) int {
	switch statusCode {
	case http.StatusBadRequest, http.StatusMethodNotAllowed:
		return ErrCodeInvalidParams
	case http.StatusUnauthorized:
		return ErrCodeUnauthorized
	case http.StatusForbidden:
		return ErrCodeForbidden
	case http.StatusNotFound:
		return ErrCodeResourceAbsent
	case http.StatusConflict:
		return ErrCodeConflict
	case http.StatusTooManyRequests:
		return ErrCodeRateLimited
	case http.StatusBadGateway:
		return ErrCodeBadGateway
	default:
		return ErrCodeInternal
	}
}
