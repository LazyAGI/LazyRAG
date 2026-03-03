package db

import (
	"net/http"

	"lazyrag/core/common"
)

// TableService stub handlers. TODO: implement later.

func GetMeta(w http.ResponseWriter, r *http.Request) { common.ReplyJSON(w, map[string]any{}) /* TODO */ }
func FindMeta(w http.ResponseWriter, r *http.Request) {
	common.ReplyJSON(w, map[string]any{}) /* TODO */
}
func QueryTable(w http.ResponseWriter, r *http.Request) {
	common.ReplyJSON(w, map[string]any{}) /* TODO */
}
