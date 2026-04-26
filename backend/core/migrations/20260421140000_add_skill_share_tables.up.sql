CREATE TABLE IF NOT EXISTS "skill_share_tasks" (
  "id" varchar(36),
  "source_user_id" varchar(255) NOT NULL,
  "source_user_name" varchar(255) NOT NULL DEFAULT '',
  "source_skill_id" varchar(36) NOT NULL,
  "source_category" varchar(128) NOT NULL DEFAULT '',
  "source_parent_skill_name" varchar(255) NOT NULL DEFAULT '',
  "source_relative_root" varchar(1024) NOT NULL DEFAULT '',
  "source_storage_root" text NOT NULL DEFAULT '',
  "message" text,
  "created_at" timestamptz NOT NULL,
  "updated_at" timestamptz NOT NULL,
  PRIMARY KEY ("id")
);
CREATE INDEX IF NOT EXISTS "idx_skill_share_tasks_source_user" ON "skill_share_tasks" ("source_user_id");

CREATE TABLE IF NOT EXISTS "skill_share_items" (
  "id" varchar(36),
  "share_task_id" varchar(36) NOT NULL,
  "target_user_id" varchar(255) NOT NULL,
  "target_user_name" varchar(255) NOT NULL DEFAULT '',
  "status" varchar(32) NOT NULL,
  "target_relative_root" varchar(1024) NOT NULL DEFAULT '',
  "target_storage_path" text NOT NULL DEFAULT '',
  "accepted_at" timestamptz,
  "rejected_at" timestamptz,
  "target_root_skill_id" varchar(36) NOT NULL DEFAULT '',
  "error_message" text,
  "created_at" timestamptz NOT NULL,
  "updated_at" timestamptz NOT NULL,
  PRIMARY KEY ("id")
);
CREATE INDEX IF NOT EXISTS "idx_skill_share_items_target_user" ON "skill_share_items" ("share_task_id","target_user_id","status");
