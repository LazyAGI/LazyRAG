-- 20260321031000_drop_task_local_state_columns
-- +migrate Down

ALTER TABLE IF EXISTS "tasks"
  ADD COLUMN IF NOT EXISTS "task_state" text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS "err_msg" text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS "start_time" timestamptz,
  ADD COLUMN IF NOT EXISTS "finish_time" timestamptz;

CREATE INDEX IF NOT EXISTS "idx_tasks_task_state" ON "tasks" ("task_state");
CREATE INDEX IF NOT EXISTS "idx_tasks_dataset_id_task_state" ON "tasks" ("dataset_id", "task_state");
