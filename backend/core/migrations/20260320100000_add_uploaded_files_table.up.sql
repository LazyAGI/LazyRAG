-- 20260320100000_add_uploaded_files_table
-- +migrate Up
-- String sizes align with documents/tasks id columns and datasets (varchar(255) for dataset_id).

CREATE TABLE IF NOT EXISTS "uploaded_files" (
  "id" bigserial,
  "upload_file_id" varchar(128) NOT NULL,
  "dataset_id" varchar(255) NOT NULL,
  "tenant_id" varchar(36) NOT NULL,
  "task_id" varchar(128) NOT NULL DEFAULT '',
  "document_id" varchar(128) NOT NULL DEFAULT '',
  "status" varchar(64) NOT NULL DEFAULT '',
  "ext" json,
  "create_user_id" varchar(255) NOT NULL,
  "create_user_name" varchar(255) NOT NULL,
  "created_at" timestamptz NOT NULL,
  "updated_at" timestamptz NOT NULL,
  "deleted_at" timestamptz,
  PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX IF NOT EXISTS "uk_uploaded_files_upload_file_id" ON "uploaded_files" ("upload_file_id");
CREATE INDEX IF NOT EXISTS "idx_uploaded_files_dataset_id" ON "uploaded_files" ("dataset_id");
CREATE INDEX IF NOT EXISTS "idx_uploaded_files_tenant_id" ON "uploaded_files" ("tenant_id");
CREATE INDEX IF NOT EXISTS "idx_uploaded_files_task_id" ON "uploaded_files" ("task_id");
CREATE INDEX IF NOT EXISTS "idx_uploaded_files_document_id" ON "uploaded_files" ("document_id");
CREATE INDEX IF NOT EXISTS "idx_uploaded_files_status" ON "uploaded_files" ("status");
