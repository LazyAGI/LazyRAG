package doc

import (
	"net/http"

	"lazyrag/core/common"
)

// TaskService 占位实现（直接暴露 Task，不经 Job），后续补全。

func ListTasks(w http.ResponseWriter, r *http.Request) {
	common.ReplyJSON(w, map[string]any{}) /* TODO */
}
func CreateTask(w http.ResponseWriter, r *http.Request) {
	common.ReplyJSON(w, map[string]any{}) /* TODO */
}
func GetTask(w http.ResponseWriter, r *http.Request)      { common.ReplyJSON(w, map[string]any{}) /* TODO */ }
func DeleteTask(w http.ResponseWriter, r *http.Request)   { w.WriteHeader(http.StatusOK) /* TODO */ }
func CancelTask(w http.ResponseWriter, r *http.Request)   { w.WriteHeader(http.StatusOK) /* TODO */ }
func SuspendTask(w http.ResponseWriter, r *http.Request)  { w.WriteHeader(http.StatusOK) /* TODO */ }
func ResumeTask(w http.ResponseWriter, r *http.Request)   { w.WriteHeader(http.StatusOK) /* TODO */ }
func TaskCallback(w http.ResponseWriter, r *http.Request) { w.WriteHeader(http.StatusOK) /* TODO */ }
