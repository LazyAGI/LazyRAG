-- 20260318120000_add_core_documents_tasks_diff
-- +migrate Up

-- Core-maintained diff tables for schema-B lazy_llm_server.*
-- These tables live in schema A (same schema as existing core tables).

CREATE TABLE IF NOT EXISTS "documents" (
  "id" bigserial,
  "doc_id" text NOT NULL,
  "dataset_id" text NOT NULL,
  "display_name" text NOT NULL DEFAULT '',
  "p_id" text NOT NULL DEFAULT '',
  "tags" json,
  "file_id" text NOT NULL DEFAULT '',
  "ext" json,
  "create_user_id" varchar(255) NOT NULL,
  "create_user_name" varchar(255) NOT NULL,
  "created_at" timestamptz NOT NULL,
  "updated_at" timestamptz NOT NULL,
  "deleted_at" timestamptz,
  PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX IF NOT EXISTS "uk_documents_doc_id" ON "documents" ("doc_id");
CREATE INDEX IF NOT EXISTS "idx_documents_dataset_id" ON "documents" ("dataset_id");
CREATE INDEX IF NOT EXISTS "idx_documents_p_id" ON "documents" ("p_id");

CREATE TABLE IF NOT EXISTS "tasks" (
  "id" bigserial,
  "task_id" text NOT NULL,
  "doc_id" text,
  "kb_id" text,
  "algo_id" text,
  "dataset_id" text NOT NULL,
  "ext" json,
  "create_user_id" varchar(255) NOT NULL,
  "create_user_name" varchar(255) NOT NULL,
  "created_at" timestamptz NOT NULL,
  "updated_at" timestamptz NOT NULL,
  "deleted_at" timestamptz,
  PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX IF NOT EXISTS "uk_tasks_task_id" ON "tasks" ("task_id");
CREATE INDEX IF NOT EXISTS "idx_tasks_dataset_id" ON "tasks" ("dataset_id");

CREATE INDEX IF NOT EXISTS "idx_tasks_doc_id" ON "tasks" ("doc_id");
CREATE INDEX IF NOT EXISTS "idx_tasks_kb_id" ON "tasks" ("kb_id");
CREATE INDEX IF NOT EXISTS "idx_tasks_algo_id" ON "tasks" ("algo_id");

