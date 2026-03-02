package main

import (
	"encoding/json"
	"log"
	"net/http"
)

// handleAPI registers a route with required permissions (for extract_api_permissions.py).
func handleAPI(mux *http.ServeMux, method, path string, perms []string, h http.HandlerFunc) {
	mux.HandleFunc(path, func(w http.ResponseWriter, r *http.Request) {
		if r.Method != method {
			http.Error(w, "Method Not Allowed", http.StatusMethodNotAllowed)
			return
		}
		h(w, r)
	})
}

func main() {
	mux := http.NewServeMux()
	mux.HandleFunc("/hello", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "Method Not Allowed", http.StatusMethodNotAllowed)
			return
		}
		reply(w, map[string]string{"message": "Hello from Backend"})
	})
	mux.HandleFunc("/admin", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "Method Not Allowed", http.StatusMethodNotAllowed)
			return
		}
		reply(w, map[string]string{"message": "Admin only area"})
	})

	handleAPI(mux, "GET", "/api/hello", []string{"user.read"}, func(w http.ResponseWriter, r *http.Request) {
		reply(w, map[string]string{"message": "Hello from Backend"})
	})
	handleAPI(mux, "GET", "/api/admin", []string{"document.write"}, func(w http.ResponseWriter, r *http.Request) {
		reply(w, map[string]string{"message": "Admin only area"})
	})

	registerAllRoutes(mux)

	log.Print("Core listening on :8000")
	log.Fatal(http.ListenAndServe(":8000", mux))
}

func reply(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(v)
}
