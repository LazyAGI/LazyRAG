-- 20260319180000_expand_tasks_and_add_upload_sessions
-- +migrate Down

DROP TABLE IF EXISTS "upload_sessions";

DROP INDEX IF EXISTS "idx_tasks_dataset_id_task_state";
DROP INDEX IF EXISTS "idx_tasks_target_dataset_id";
DROP INDEX IF EXISTS "idx_tasks_document_pid";
DROP INDEX IF EXISTS "idx_tasks_task_type";
DROP INDEX IF EXISTS "idx_tasks_task_state";

ALTER TABLE IF EXISTS "tasks"
  DROP COLUMN IF EXISTS "finish_time",
  DROP COLUMN IF EXISTS "start_time",
  DROP COLUMN IF EXISTS "err_msg",
  DROP COLUMN IF EXISTS "display_name",
  DROP COLUMN IF EXISTS "target_dataset_id",
  DROP COLUMN IF EXISTS "target_pid",
  DROP COLUMN IF EXISTS "document_pid",
  DROP COLUMN IF EXISTS "task_state",
  DROP COLUMN IF EXISTS "task_type";
