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
	CodeOK    = 0
	CodeError = 1
)

func ReplyOK(w http.ResponseWriter, data any) {
	reply(w, CodeOK, "ok", data, http.StatusOK)
}

func ReplyErr(w http.ResponseWriter, message string, statusCode int) {
	reply(w, CodeError, message, nil, statusCode)
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
