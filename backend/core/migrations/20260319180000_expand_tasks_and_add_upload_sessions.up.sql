-- 20260319180000_expand_tasks_and_add_upload_sessions
-- +migrate Up

ALTER TABLE IF EXISTS "tasks"
  ADD COLUMN IF NOT EXISTS "task_type" text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS "task_state" text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS "document_pid" text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS "target_pid" text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS "target_dataset_id" text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS "display_name" text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS "err_msg" text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS "start_time" timestamptz,
  ADD COLUMN IF NOT EXISTS "finish_time" timestamptz;

CREATE INDEX IF NOT EXISTS "idx_tasks_task_state" ON "tasks" ("task_state");
CREATE INDEX IF NOT EXISTS "idx_tasks_task_type" ON "tasks" ("task_type");
CREATE INDEX IF NOT EXISTS "idx_tasks_document_pid" ON "tasks" ("document_pid");
CREATE INDEX IF NOT EXISTS "idx_tasks_target_dataset_id" ON "tasks" ("target_dataset_id");
CREATE INDEX IF NOT EXISTS "idx_tasks_dataset_id_task_state" ON "tasks" ("dataset_id", "task_state");

CREATE TABLE IF NOT EXISTS "upload_sessions" (
  "id" bigserial,
  "upload_id" text NOT NULL,
  "task_id" text NOT NULL,
  "dataset_id" text NOT NULL,
  "tenant_id" text NOT NULL,
  "document_id" text NOT NULL,
  "upload_state" text NOT NULL DEFAULT '',
  "ext" json,
  "create_user_id" varchar(255) NOT NULL,
  "create_user_name" varchar(255) NOT NULL,
  "created_at" timestamptz NOT NULL,
  "updated_at" timestamptz NOT NULL,
  "deleted_at" timestamptz,
  PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX IF NOT EXISTS "uk_upload_sessions_upload_id" ON "upload_sessions" ("upload_id");
CREATE INDEX IF NOT EXISTS "idx_upload_sessions_task_id" ON "upload_sessions" ("task_id");
CREATE INDEX IF NOT EXISTS "idx_upload_sessions_dataset_id" ON "upload_sessions" ("dataset_id");
CREATE INDEX IF NOT EXISTS "idx_upload_sessions_document_id" ON "upload_sessions" ("document_id");
CREATE INDEX IF NOT EXISTS "idx_upload_sessions_upload_state" ON "upload_sessions" ("upload_state");
