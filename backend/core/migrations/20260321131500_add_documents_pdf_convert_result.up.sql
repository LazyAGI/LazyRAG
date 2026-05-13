-- 20260321131500_add_documents_pdf_convert_result (merged full init)
-- +migrate Up

CREATE TABLE IF NOT EXISTS "schema_migration_history" (
  "version" bigint NOT NULL,
  "name" varchar(255) NOT NULL DEFAULT '',
  "applied_at" timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY ("version")
);

-- ACL tables

CREATE TABLE "acl_visibility" (
  "id" bigserial,
  "resource_id" varchar(255),
  "level" varchar(32),
  PRIMARY KEY ("id")
);
CREATE INDEX IF NOT EXISTS "idx_acl_visibility_resource_id" ON "acl_visibility" ("resource_id");

CREATE TABLE "acl_rows" (
  "id" bigserial,
  "resource_type" varchar(32),
  "resource_id" varchar(255),
  "grantee_type" varchar(32),
  "target_id" varchar(255),
  "permission" varchar(32),
  "created_by" varchar(255),
  "created_at" timestamptz,
  "expires_at" timestamptz,
  PRIMARY KEY ("id")
);
CREATE INDEX IF NOT EXISTS "idx_acl_resource" ON "acl_rows" ("resource_type","resource_id");

CREATE TABLE "acl_kbs" (
  "id" varchar(64),
  "name" varchar(255),
  "owner_id" varchar(255),
  "visibility" varchar(32),
  PRIMARY KEY ("id")
);

CREATE TABLE "acl_user_groups" (
  "user_id" varchar(255),
  "group_id" varchar(255),
  PRIMARY KEY ("user_id","group_id")
);

CREATE TABLE IF NOT EXISTS "acl_groups" (
  "id" varchar(255),
  "name" varchar(255) NOT NULL DEFAULT '',
  PRIMARY KEY ("id")
);

-- Prompt / conversation tables

CREATE TABLE "prompts" (
  "id" varchar(64),
  "name" varchar(255) NOT NULL,
  "content" text NOT NULL,
  "create_user_id" varchar(255) NOT NULL,
  "create_user_name" varchar(255) NOT NULL,
  "created_at" timestamptz NOT NULL,
  "updated_at" timestamptz NOT NULL,
  "deleted_at" timestamptz,
  PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX IF NOT EXISTS "uk_prompts_user_name" ON "prompts" ("create_user_id", "name");

CREATE TABLE "default_prompts" (
  "id" bigserial,
  "prompt_id" varchar(64) NOT NULL,
  "prompt_name" varchar(255) NOT NULL,
  "create_user_id" varchar(255) NOT NULL,
  "create_user_name" varchar(255) NOT NULL,
  "created_at" timestamptz NOT NULL,
  "updated_at" timestamptz NOT NULL,
  "deleted_at" timestamptz,
  PRIMARY KEY ("id")
);

CREATE TABLE "multi_answers_switches" (
  "id" serial,
  "status" integer NOT NULL DEFAULT 0,
  "create_user_id" varchar(255) NOT NULL,
  "create_user_name" varchar(255) NOT NULL,
  "created_at" timestamptz NOT NULL,
  "updated_at" timestamptz NOT NULL,
  "deleted_at" timestamptz,
  PRIMARY KEY ("id")
);

CREATE TABLE "conversations" (
  "id" varchar(36),
  "display_name" varchar(255),
  "channel_id" varchar(36) NOT NULL DEFAULT 'default',
  "search_config" json,
  "application_id" varchar(64) DEFAULT '',
  "ext" json,
  "model" varchar(64) DEFAULT '',
  "models" json,
  "chat_times" integer NOT NULL DEFAULT 0,
  "create_user_id" varchar(255) NOT NULL,
  "create_user_name" varchar(255) NOT NULL,
  "created_at" timestamptz NOT NULL,
  "updated_at" timestamptz NOT NULL,
  "deleted_at" timestamptz,
  PRIMARY KEY ("id")
);

CREATE TABLE "chat_histories" (
  "id" varchar(36),
  "seq" bigint NOT NULL,
  "conversation_id" varchar(36) NOT NULL,
  "raw_content" text,
  "retrieval_result" json,
  "content" text,
  "result" text,
  "feed_back" bigint DEFAULT 0,
  "reason" varchar(255),
  "expected_answer" text,
  "ext" json,
  "version" varchar(128) DEFAULT '2.3',
  "create_time" timestamptz NOT NULL,
  "update_time" timestamptz NOT NULL,
  PRIMARY KEY ("id")
);
CREATE INDEX IF NOT EXISTS "idx_chat_histories_conversation_id" ON "chat_histories" ("conversation_id");

CREATE TABLE "multi_answers_chat_histories" (
  "id" varchar(36),
  "seq" bigint NOT NULL,
  "conversation_id" varchar(36) NOT NULL,
  "raw_content" text,
  "retrieval_result" json,
  "content" text,
  "result" text,
  "feed_back" bigint DEFAULT 0,
  "reason" varchar(255),
  "ext" json,
  "endpoint" varchar(512),
  "create_time" timestamptz NOT NULL,
  "update_time" timestamptz NOT NULL,
  PRIMARY KEY ("id")
);
CREATE INDEX IF NOT EXISTS "idx_multi_answers_chat_histories_conversation_id" ON "multi_answers_chat_histories" ("conversation_id");

-- Dataset tables

CREATE TABLE IF NOT EXISTS "datasets" (
  "id" varchar(255),
  "kb_id" varchar(255) NOT NULL,
  "display_name" varchar(255) NOT NULL,
  "desc" text NOT NULL,
  "cover_image" varchar(255) NOT NULL,
  "resource_uid" varchar(36) NOT NULL,
  "bucket_name" varchar(255) NOT NULL,
  "oss_path" varchar(255) NOT NULL,
  "dataset_info" json,
  "dataset_state" smallint NOT NULL,
  "embedding_model" varchar(255) NOT NULL,
  "embedding_model_provider" varchar(255) NOT NULL,
  "share_type" smallint NOT NULL,
  "shared_at" timestamptz,
  "tenant_id" varchar(36) NOT NULL,
  "is_demonstrate" boolean NOT NULL DEFAULT false,
  "type" smallint NOT NULL DEFAULT 1,
  "ext" json,
  "create_user_id" varchar(255) NOT NULL,
  "create_user_name" varchar(255) NOT NULL,
  "created_at" timestamptz NOT NULL,
  "updated_at" timestamptz NOT NULL,
  "deleted_at" timestamptz,
  PRIMARY KEY ("id")
);
CREATE INDEX IF NOT EXISTS "idx_resource_uid" ON "datasets" ("resource_uid");
CREATE INDEX IF NOT EXISTS "idx_create_user_id" ON "datasets" ("create_user_id");
CREATE INDEX IF NOT EXISTS "idx_datasets_kb_id" ON "datasets" ("kb_id");

CREATE TABLE IF NOT EXISTS "dataset_members" (
  "id" varchar(36),
  "dataset_id" varchar(36) NOT NULL,
  "tenant_member_id" varchar(36) NOT NULL,
  "role" boolean NOT NULL,
  "resource_id" varchar(36) NOT NULL,
  "name" varchar(64) NOT NULL,
  "create_time" timestamptz NOT NULL,
  "update_time" timestamptz NOT NULL,
  PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX IF NOT EXISTS "datasetmember_dataset_id_tenant_member_id_role" ON "dataset_members" ("dataset_id","tenant_member_id","role");
CREATE INDEX IF NOT EXISTS "datasetmember_tenant_member_id" ON "dataset_members" ("tenant_member_id");
CREATE INDEX IF NOT EXISTS "datasetmember_resource_id" ON "dataset_members" ("resource_id");
CREATE INDEX IF NOT EXISTS "datasetmember_name" ON "dataset_members" ("name");

CREATE TABLE IF NOT EXISTS "default_datasets" (
  "id" bigserial,
  "dataset_id" varchar(64) NOT NULL,
  "dataset_name" varchar(255) NOT NULL,
  "create_user_id" varchar(255) NOT NULL,
  "create_user_name" varchar(255) NOT NULL,
  "created_at" timestamptz NOT NULL,
  "updated_at" timestamptz NOT NULL,
  "deleted_at" timestamptz,
  PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX IF NOT EXISTS "ukx_create_user_id_dataset_id" ON "default_datasets" ("create_user_id","dataset_id");

-- Uploaded files table

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

-- Documents, tasks, upload_sessions (final schema with string PKs)

CREATE TABLE documents (
  id varchar(128) PRIMARY KEY,
  lazyllm_doc_id varchar(128) NOT NULL DEFAULT '',
  dataset_id varchar(255) NOT NULL,
  display_name varchar(512) NOT NULL DEFAULT '',
  p_id varchar(255) NOT NULL DEFAULT '',
  tags json,
  file_id varchar(128) NOT NULL DEFAULT '',
  pdf_convert_result varchar(64) NOT NULL DEFAULT '',
  ext json,
  create_user_id varchar(255) NOT NULL,
  create_user_name varchar(255) NOT NULL,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  deleted_at timestamptz
);
CREATE INDEX idx_documents_lazyllm_doc_id ON documents (lazyllm_doc_id);
CREATE INDEX idx_documents_dataset_id ON documents (dataset_id);
CREATE INDEX idx_documents_p_id ON documents (p_id);

CREATE TABLE tasks (
  id varchar(128) PRIMARY KEY,
  lazyllm_task_id varchar(128) NOT NULL DEFAULT '',
  doc_id varchar(128),
  kb_id varchar(255),
  algo_id varchar(255),
  dataset_id varchar(255) NOT NULL,
  task_type varchar(128) NOT NULL DEFAULT '',
  document_pid varchar(255) NOT NULL DEFAULT '',
  target_pid varchar(255) NOT NULL DEFAULT '',
  target_dataset_id varchar(255) NOT NULL DEFAULT '',
  display_name varchar(512) NOT NULL DEFAULT '',
  ext json,
  create_user_id varchar(255) NOT NULL,
  create_user_name varchar(255) NOT NULL,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  deleted_at timestamptz
);
CREATE INDEX idx_tasks_lazyllm_task_id ON tasks (lazyllm_task_id);
CREATE INDEX idx_tasks_doc_id ON tasks (doc_id);
CREATE INDEX idx_tasks_dataset_id ON tasks (dataset_id);
CREATE INDEX idx_tasks_kb_id ON tasks (kb_id);
CREATE INDEX idx_tasks_algo_id ON tasks (algo_id);
CREATE INDEX idx_tasks_task_type ON tasks (task_type);
CREATE INDEX idx_tasks_document_pid ON tasks (document_pid);
CREATE INDEX idx_tasks_target_dataset_id ON tasks (target_dataset_id);

CREATE TABLE upload_sessions (
  id bigserial PRIMARY KEY,
  upload_id varchar(128) NOT NULL,
  task_id varchar(128) NOT NULL,
  dataset_id varchar(255) NOT NULL,
  tenant_id varchar(36) NOT NULL,
  document_id varchar(128) NOT NULL,
  upload_state varchar(64) NOT NULL DEFAULT '',
  ext json,
  create_user_id varchar(255) NOT NULL,
  create_user_name varchar(255) NOT NULL,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  deleted_at timestamptz
);
CREATE UNIQUE INDEX uk_upload_sessions_upload_id ON upload_sessions (upload_id);
CREATE INDEX idx_upload_sessions_task_id ON upload_sessions (task_id);
CREATE INDEX idx_upload_sessions_dataset_id ON upload_sessions (dataset_id);
CREATE INDEX idx_upload_sessions_document_id ON upload_sessions (document_id);
CREATE INDEX idx_upload_sessions_upload_state ON upload_sessions (upload_state);
