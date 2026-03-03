package doc

import (
	"net/http"

	"lazyrag/core/common"
)

// DatasetMemberService stub handlers. TODO: implement later.

func ListDatasetMembers(w http.ResponseWriter, r *http.Request) {
	common.ReplyJSON(w, map[string]any{}) /* TODO */
}
func GetDatasetMember(w http.ResponseWriter, r *http.Request) {
	common.ReplyJSON(w, map[string]any{}) /* TODO */
}
func DeleteDatasetMember(w http.ResponseWriter, r *http.Request) {
	w.WriteHeader(http.StatusOK) /* TODO */
}
func UpdateDatasetMember(w http.ResponseWriter, r *http.Request) {
	common.ReplyJSON(w, map[string]any{}) /* TODO */
}
func SearchDatasetMember(w http.ResponseWriter, r *http.Request) {
	common.ReplyJSON(w, map[string]any{}) /* TODO */
}
func BatchAddDatasetMember(w http.ResponseWriter, r *http.Request) {
	common.ReplyJSON(w, map[string]any{}) /* TODO */
}
