package db

import (
	"net/http"
)

// 以下为 TableService 接口桩，TODO 稍后实现。

func GetMeta(w http.ResponseWriter, r *http.Request)    { replyJSON(w, map[string]any{}) /* TODO */ }
func FindMeta(w http.ResponseWriter, r *http.Request)   { replyJSON(w, map[string]any{}) /* TODO */ }
func QueryTable(w http.ResponseWriter, r *http.Request) { replyJSON(w, map[string]any{}) /* TODO */ }
