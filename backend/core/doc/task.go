package doc

import (
	"net/http"
)

// TaskService stub handlers (expose Task directly, not via Job). TODO: implement later.

func ListTasks(w http.ResponseWriter, r *http.Request)    { replyJSON(w, map[string]any{}) /* TODO */ }
func CreateTask(w http.ResponseWriter, r *http.Request)   { replyJSON(w, map[string]any{}) /* TODO */ }
func GetTask(w http.ResponseWriter, r *http.Request)      { replyJSON(w, map[string]any{}) /* TODO */ }
func DeleteTask(w http.ResponseWriter, r *http.Request)   { w.WriteHeader(http.StatusOK) /* TODO */ }
func CancelTask(w http.ResponseWriter, r *http.Request)   { w.WriteHeader(http.StatusOK) /* TODO */ }
func SuspendTask(w http.ResponseWriter, r *http.Request)  { w.WriteHeader(http.StatusOK) /* TODO */ }
func ResumeTask(w http.ResponseWriter, r *http.Request)   { w.WriteHeader(http.StatusOK) /* TODO */ }
func TaskCallback(w http.ResponseWriter, r *http.Request) { w.WriteHeader(http.StatusOK) /* TODO */ }
