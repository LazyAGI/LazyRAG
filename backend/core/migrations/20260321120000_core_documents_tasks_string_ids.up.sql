-- 20260321120000_core_documents_tasks_string_ids
-- +migrate Up
-- Destructive: drop and recreate core documents/tasks (and upload_sessions) for string PK + lazyllm_* ids.
-- Column types align with readonlyorm lazyllm_* tables and core datasets (varchar(255) for dataset/kb/algo ids).

DROP TABLE IF EXISTS upload_sessions CASCADE;
DROP TABLE IF EXISTS tasks CASCADE;
DROP TABLE IF EXISTS documents CASCADE;

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
