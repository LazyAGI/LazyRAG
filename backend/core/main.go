package main

import (
	"context"
	_ "embed"
	"encoding/json"
	"net/http"
	"os"
	"strings"

	"github.com/gorilla/mux"
	"gopkg.in/yaml.v3"
	"lazyrag/core/acl"
	"lazyrag/core/store"
	"lazyrag/core/common"
	"lazyrag/core/common/orm"
	"lazyrag/core/common/readonlyorm"
	"lazyrag/core/log"
	"lazyrag/core/migrate"
)

//go:embed docs.html
var swaggerUIHTML []byte

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
	if err := migrate.RunUp(); err != nil {
		log.Logger.Fatal().Err(err).Msg("run SQL migrations failed")
	}

	readonlyDriver := strings.TrimSpace(os.Getenv("LAZYRAG_READONLY_DB_DRIVER"))
	readonlyDSN := strings.TrimSpace(os.Getenv("LAZYRAG_READONLY_DB_DSN"))
	if readonlyDriver == "" {
		readonlyDriver = strings.TrimSpace(os.Getenv("LAZYRAG_LAZYLLM_DB_DRIVER"))
	}
	if readonlyDSN == "" {
		readonlyDSN = strings.TrimSpace(os.Getenv("LAZYRAG_LAZYLLM_DB_DSN"))
	}
	readonlyDB := db
	if readonlyDriver != "" || readonlyDSN != "" {
		if readonlyDriver == "" {
			readonlyDriver = driver
		}
		if readonlyDSN == "" {
			log.Logger.Fatal().Msg("LAZYRAG_READONLY_DB_DSN is empty")
		}
		readonlyDB = orm.MustConnect(readonlyDriver, readonlyDSN)
	}

	// Optional: validate readonly external tables at startup.
	// Enable with LAZYRAG_READONLY_VALIDATE=1 and list tables via LAZYRAG_READONLY_TABLES.
	if strings.TrimSpace(os.Getenv("LAZYRAG_READONLY_VALIDATE")) == "1" {
		sqlDB, err := readonlyDB.DB.DB()
		if err != nil {
			log.Logger.Fatal().Err(err).Msg("get readonly sql.DB failed")
		}
		specs := readonlyorm.Specs()
		if len(specs) == 0 {
			log.Logger.Warn().Msg("readonly schema validation enabled but no LAZYRAG_READONLY_TABLES configured; skipping")
		} else if err := readonlyorm.Validate(context.Background(), sqlDB, specs); err != nil {
			log.Logger.Fatal().Err(err).Msg("readonly schema validation failed")
		} else {
			log.Logger.Info().Int("tables", len(specs)).Msg("readonly schema validation ok")
		}
	}
	acl.InitStore(db)
	log.Logger.Info().Str("driver", driver).Msg("ACL store initialized")

	// 对话/提示词存储初始化（DB + Redis）。DB 复用 ACL 连接；Redis 用于会话流式/续传/停止等能力（与 neutrino 对齐）。
	store.Init(db.DB, readonlyDB.DB, store.MustRedisFromEnv())

	r := mux.NewRouter()
	r.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("ok"))
	}).Methods(http.MethodGet)
	handleAPI(r, "GET", "/hello", []string{"user.read"}, func(w http.ResponseWriter, r *http.Request) {
		common.ReplyJSON(w, map[string]string{"message": "Hello from Backend"})
	})
	handleAPI(r, "GET", "/admin", []string{"document.write"}, func(w http.ResponseWriter, r *http.Request) {
		common.ReplyJSON(w, map[string]string{"message": "Admin only area"})
	})
	registerAllRoutes(r)

	// 启动时从已注册路由自动生成 OpenAPI spec，无需手维护 doc_swag.go / swag init
	openAPIJSON, err := buildOpenAPISpecFromRouter(r)
	if err != nil {
		log.Logger.Fatal().Err(err).Msg("build OpenAPI spec from router failed")
	}
	r.HandleFunc("/openapi.json", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Write(openAPIJSON)
	}).Methods(http.MethodGet)
	r.HandleFunc("/openapi.yaml", func(w http.ResponseWriter, r *http.Request) {
		var m map[string]interface{}
		if err := json.Unmarshal(openAPIJSON, &m); err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		out, err := yaml.Marshal(m)
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		w.Header().Set("Content-Type", "application/x-yaml")
		w.Write(out)
	}).Methods(http.MethodGet)
	r.HandleFunc("/docs", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		w.Write(swaggerUIHTML)
	}).Methods(http.MethodGet)

	log.Logger.Info().Msg("Core listening on :8000")
	if err := http.ListenAndServe(":8000", r); err != nil {
		log.Logger.Fatal().Err(err).Msg("http listen failed")
	}
}
