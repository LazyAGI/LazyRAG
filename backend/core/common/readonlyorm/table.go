package readonlyorm

import (
	"os"
	"strings"
)

// LazyLLMSchema returns the schema name that contains readonly external tables.
// Prefer LAZYMIND_READONLY_SCHEMA, and keep LAZYMIND_LAZYLLM_SCHEMA as backward-compatible fallback.
func LazyLLMSchema() string {
	if v := strings.TrimSpace(os.Getenv("LAZYMIND_READONLY_SCHEMA")); v != "" {
		return v
	}
	if v := strings.TrimSpace(os.Getenv("LAZYMIND_LAZYLLM_SCHEMA")); v != "" {
		return v
	}
	return "public"
}

// Table returns a fully-qualified table name: schema.table
// Use it with GORM: db.Table(readonlyorm.Table("ragservice", "documents"))
func Table(schema, table string) string {
	s := strings.TrimSpace(schema)
	t := strings.TrimSpace(table)
	if s == "" {
		return t
	}
	return s + "." + t
}
