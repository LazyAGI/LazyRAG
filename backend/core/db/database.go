package db

import (
	"encoding/json"
	"net/http"
)

func replyJSON(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(v)
}

// DatabaseService (RAG) stub handlers. TODO: implement later.

func GetUserDatabaseTags(w http.ResponseWriter, r *http.Request) {
	replyJSON(w, map[string]any{}) /* TODO */
}
func GetUserDatabases(w http.ResponseWriter, r *http.Request) {
	replyJSON(w, map[string]any{}) /* TODO */
}
func CreateDatabase(w http.ResponseWriter, r *http.Request) { replyJSON(w, map[string]any{}) /* TODO */ }
func GetUserDatabaseSummaries(w http.ResponseWriter, r *http.Request) {
	replyJSON(w, map[string]any{}) /* TODO */
}
func ValidateConnection(w http.ResponseWriter, r *http.Request) {
	replyJSON(w, map[string]any{}) /* TODO */
}
func DeleteDatabase(w http.ResponseWriter, r *http.Request) { w.WriteHeader(http.StatusOK) /* TODO */ }
func GetDatabaseTables(w http.ResponseWriter, r *http.Request) {
	replyJSON(w, map[string]any{}) /* TODO */
}
func UpdateTableCell(w http.ResponseWriter, r *http.Request) {
	replyJSON(w, map[string]any{}) /* TODO */
}
func ListTableRows(w http.ResponseWriter, r *http.Request)  { replyJSON(w, map[string]any{}) /* TODO */ }
func UpdateDatabase(w http.ResponseWriter, r *http.Request) { replyJSON(w, map[string]any{}) /* TODO */ }
