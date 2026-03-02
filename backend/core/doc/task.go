package doc

import (
	"net/http"
)

// 以下为 TaskService 接口桩（直接暴露 Task，不通过 Job），TODO 稍后实现。

func ListTasks(w http.ResponseWriter, r *http.Request)    { replyJSON(w, map[string]any{}) /* TODO */ }
func CreateTask(w http.ResponseWriter, r *http.Request)   { replyJSON(w, map[string]any{}) /* TODO */ }
func GetTask(w http.ResponseWriter, r *http.Request)      { replyJSON(w, map[string]any{}) /* TODO */ }
func DeleteTask(w http.ResponseWriter, r *http.Request)   { w.WriteHeader(http.StatusOK) /* TODO */ }
func CancelTask(w http.ResponseWriter, r *http.Request)   { w.WriteHeader(http.StatusOK) /* TODO */ }
func SuspendTask(w http.ResponseWriter, r *http.Request)  { w.WriteHeader(http.StatusOK) /* TODO */ }
func ResumeTask(w http.ResponseWriter, r *http.Request)   { w.WriteHeader(http.StatusOK) /* TODO */ }
func TaskCallback(w http.ResponseWriter, r *http.Request) { w.WriteHeader(http.StatusOK) /* TODO */ }
