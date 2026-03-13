package db

import (
	"net/http"

	"lazyrag/core/common"
)

// TableService 占位实现，后续补全。

func GetMeta(w http.ResponseWriter, r *http.Request) { common.ReplyJSON(w, map[string]any{}) /* TODO */ }
func FindMeta(w http.ResponseWriter, r *http.Request) {
	common.ReplyJSON(w, map[string]any{}) /* TODO */
}
func QueryTable(w http.ResponseWriter, r *http.Request) {
	common.ReplyJSON(w, map[string]any{}) /* TODO */
}
