package doc

import (
	"net/http"

	"lazyrag/core/common"
)

// Internal API stub handlers. TODO: implement later.

func GetDatasetInternal(w http.ResponseWriter, r *http.Request) {
	common.ReplyJSON(w, map[string]any{}) /* TODO */
}
func KnowledgeRetrieve(w http.ResponseWriter, r *http.Request) {
	common.ReplyJSON(w, map[string]any{}) /* TODO */
}
