CREATE TABLE IF NOT EXISTS "agent_user_active_threads" (
  "user_id" varchar(255) PRIMARY KEY,
  "thread_id" varchar(128) NOT NULL DEFAULT '',
  "status" varchar(32) NOT NULL DEFAULT 'creating',
  "create_token" varchar(64) NOT NULL DEFAULT '',
  "lease_until" timestamptz NOT NULL,
  "created_at" timestamptz NOT NULL,
  "updated_at" timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS "idx_agent_user_active_threads_thread_id"
  ON "agent_user_active_threads" ("thread_id");
CREATE INDEX IF NOT EXISTS "idx_agent_user_active_threads_status_lease"
  ON "agent_user_active_threads" ("status", "lease_until");
