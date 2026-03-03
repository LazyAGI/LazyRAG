package common

import (
	"encoding/json"
	"net/http"
)

// ReplyJSON writes v as JSON with Content-Type application/json.
func ReplyJSON(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(v)
}
