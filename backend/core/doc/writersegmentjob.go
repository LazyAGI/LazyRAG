package doc

import (
	"net/http"
)

// 以下为 WriterSegmentJob 接口桩，TODO 稍后实现。

func Submit(w http.ResponseWriter, r *http.Request) { replyJSON(w, map[string]any{}) /* TODO */ }
func Get(w http.ResponseWriter, r *http.Request)    { replyJSON(w, map[string]any{}) /* TODO */ }
