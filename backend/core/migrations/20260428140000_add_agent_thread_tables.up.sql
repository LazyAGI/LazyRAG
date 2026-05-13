CREATE TABLE IF NOT EXISTS "agent_threads" (
  "thread_id" varchar(128) PRIMARY KEY,
  "current_task_id" varchar(128) NOT NULL DEFAULT '',
  "status" varchar(32) NOT NULL DEFAULT 'created',
  "thread_payload" text NOT NULL DEFAULT '',
  "last_message_request_hash" varchar(64) NOT NULL DEFAULT '',
  "create_user_id" varchar(255) NOT NULL DEFAULT '',
  "create_user_name" varchar(255) NOT NULL DEFAULT '',
  "created_at" timestamptz NOT NULL,
  "updated_at" timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS "idx_agent_threads_current_task_id" ON "agent_threads" ("current_task_id");

CREATE TABLE IF NOT EXISTS "agent_thread_rounds" (
  "round_id" varchar(32) PRIMARY KEY,
  "thread_id" varchar(128) NOT NULL,
  "request_hash" varchar(64) NOT NULL DEFAULT '',
  "task_id" varchar(128) NOT NULL DEFAULT '',
  "status" varchar(32) NOT NULL DEFAULT 'created',
  "user_message" text NOT NULL DEFAULT '',
  "assistant_message" text NOT NULL DEFAULT '',
  "request_payload" text NOT NULL DEFAULT '',
  "created_at" timestamptz NOT NULL,
  "updated_at" timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS "idx_agent_thread_rounds_thread_id"
  ON "agent_thread_rounds" ("thread_id", "created_at");
CREATE INDEX IF NOT EXISTS "idx_agent_thread_rounds_thread_request_hash"
  ON "agent_thread_rounds" ("thread_id", "request_hash");

CREATE TABLE IF NOT EXISTS "agent_thread_records" (
  "id" varchar(32) PRIMARY KEY,
  "thread_id" varchar(128) NOT NULL,
  "round_id" varchar(32) NOT NULL DEFAULT '',
  "task_id" varchar(128) NOT NULL DEFAULT '',
  "stream_kind" varchar(32) NOT NULL,
  "record_key" varchar(64) NOT NULL,
  "event_name" varchar(128) NOT NULL DEFAULT '',
  "payload_text" text NOT NULL DEFAULT '',
  "raw_frame" text NOT NULL DEFAULT '',
  "created_at" timestamptz NOT NULL,
  "updated_at" timestamptz NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS "uk_agent_thread_records_record_key"
  ON "agent_thread_records" ("thread_id", "round_id", "stream_kind", "record_key");
CREATE INDEX IF NOT EXISTS "idx_agent_thread_records_thread_stream_id"
  ON "agent_thread_records" ("thread_id", "stream_kind", "id");
CREATE INDEX IF NOT EXISTS "idx_agent_thread_records_thread_round_id"
  ON "agent_thread_records" ("thread_id", "round_id");
CREATE INDEX IF NOT EXISTS "idx_agent_thread_records_round_stream_id"
  ON "agent_thread_records" ("round_id", "stream_kind", "id");
