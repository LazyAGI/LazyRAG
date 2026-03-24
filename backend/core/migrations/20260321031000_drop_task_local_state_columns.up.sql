-- 20260321031000_drop_task_local_state_columns
-- +migrate Up

DROP INDEX IF EXISTS "idx_tasks_dataset_id_task_state";
DROP INDEX IF EXISTS "idx_tasks_task_state";

ALTER TABLE IF EXISTS "tasks"
  DROP COLUMN IF EXISTS "finish_time",
  DROP COLUMN IF EXISTS "start_time",
  DROP COLUMN IF EXISTS "err_msg",
  DROP COLUMN IF EXISTS "task_state";
