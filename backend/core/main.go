package main

import (
	_ "embed"
	"net/http"
	"os"

	"github.com/gorilla/mux"
	"lazyrag/core/acl"
	"lazyrag/core/store"
	"lazyrag/core/common"
	"lazyrag/core/common/orm"
	"lazyrag/core/log"
)

//go:embed openapi.json
var openAPIJSON []byte

// handleAPI 注册带权限要求的路由。perms 供 extract_api_permissions.py 生成 api_permissions.json（Kong RBAC），
// 运行时不由 core 校验（由 Kong + auth-service 鉴权）。使用 gorilla/mux，同一 path 可区分方法，支持 ":action" 路径。
func handleAPI(r *mux.Router, method, path string, perms []string, h http.HandlerFunc) {
	r.HandleFunc(path, h).Methods(method)
}

func main() {
	log.Init()

	// 使用数据库初始化 ACL 存储（驱动由环境变量指定：postgres/sqlite/mysql）。
	// 未设置 ACL_DB_DRIVER 时默认使用 sqlite，数据文件 ./acl.db。
	driver := os.Getenv("ACL_DB_DRIVER")
	dsn := os.Getenv("ACL_DB_DSN")
	if driver == "" {
		driver = "sqlite"
		dsn = "./acl.db"
	} else if dsn == "" {
		log.Logger.Fatal().Msg("ACL_DB_DRIVER set but ACL_DB_DSN is empty")
	}
	db := orm.MustConnect(driver, dsn)
	acl.InitStore(db)
	log.Logger.Info().Str("driver", driver).Msg("ACL store initialized")

	// 对话/提示词存储初始化（DB + Redis）。DB 复用 ACL 连接；Redis 用于会话流式/续传/停止等能力（与 neutrino 对齐）。
	store.Init(db.DB, store.MustRedisFromEnv())

	r := mux.NewRouter()
	r.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("ok"))
	}).Methods(http.MethodGet)
	r.HandleFunc("/openapi.json", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Write(openAPIJSON)
	}).Methods(http.MethodGet)
	handleAPI(r, "GET", "/api/hello", []string{"user.read"}, func(w http.ResponseWriter, r *http.Request) {
		common.ReplyJSON(w, map[string]string{"message": "Hello from Backend"})
	})
	handleAPI(r, "GET", "/api/admin", []string{"document.write"}, func(w http.ResponseWriter, r *http.Request) {
		common.ReplyJSON(w, map[string]string{"message": "Admin only area"})
	})

	registerAllRoutes(r)

	log.Logger.Info().Msg("Core listening on :8000")
	if err := http.ListenAndServe(":8000", r); err != nil {
		log.Logger.Fatal().Err(err).Msg("http listen failed")
	}
}
