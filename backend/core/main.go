package main

import (
	"encoding/json"
	"log"
	"net/http"
	"os"

	"github.com/gorilla/mux"
	"lazyrag/core/acl"
	"lazyrag/core/common/orm"
)

// handleAPI registers a route with required permissions (for extract_api_permissions.py).
// Uses gorilla/mux so same path can have different methods and paths with ":action" are supported.
func handleAPI(r *mux.Router, method, path string, perms []string, h http.HandlerFunc) {
	r.HandleFunc(path, h).Methods(method)
}

func main() {
	// Initialize ACL store with database (postgres/sqlite/mysql via env).
	// Default: sqlite with ./acl.db when ACL_DB_DRIVER not set.
	driver := os.Getenv("ACL_DB_DRIVER")
	dsn := os.Getenv("ACL_DB_DSN")
	if driver == "" {
		driver = "sqlite"
		dsn = "./acl.db"
	} else if dsn == "" {
		log.Fatal("ACL_DB_DRIVER set but ACL_DB_DSN is empty")
	}
	db := orm.MustConnect(driver, dsn)
	acl.InitStore(db)
	log.Printf("ACL store initialized with %s", driver)

	r := mux.NewRouter()
	r.HandleFunc("/hello", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "Method Not Allowed", http.StatusMethodNotAllowed)
			return
		}
		reply(w, map[string]string{"message": "Hello from Backend"})
	}).Methods(http.MethodGet)
	r.HandleFunc("/admin", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "Method Not Allowed", http.StatusMethodNotAllowed)
			return
		}
		reply(w, map[string]string{"message": "Admin only area"})
	}).Methods(http.MethodGet)

	handleAPI(r, "GET", "/api/hello", []string{"user.read"}, func(w http.ResponseWriter, r *http.Request) {
		reply(w, map[string]string{"message": "Hello from Backend"})
	})
	handleAPI(r, "GET", "/api/admin", []string{"document.write"}, func(w http.ResponseWriter, r *http.Request) {
		reply(w, map[string]string{"message": "Admin only area"})
	})

	registerAllRoutes(r)

	log.Print("Core listening on :8000")
	log.Fatal(http.ListenAndServe(":8000", r))
}

func reply(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(v)
}
