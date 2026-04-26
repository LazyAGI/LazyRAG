-- Add foundations for memory evolution, skill metadata, session snapshots, and suggestions.

CREATE TABLE IF NOT EXISTS "system_memories" (
  "id" varchar(36),
  "content" text NOT NULL DEFAULT '',
  "content_hash" varchar(64) NOT NULL DEFAULT '',
  "version" bigint NOT NULL DEFAULT 1,
  "draft_content" text,
  "draft_source_version" bigint NOT NULL DEFAULT 0,
  "draft_status" varchar(32) NOT NULL DEFAULT '',
  "draft_updated_at" timestamptz,
  "ext" json,
  "updated_by" varchar(255) NOT NULL DEFAULT '',
  "updated_by_name" varchar(255) NOT NULL DEFAULT '',
  "created_at" timestamptz NOT NULL,
  "updated_at" timestamptz NOT NULL,
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "system_user_preferences" (
  "id" varchar(36),
  "content" text NOT NULL DEFAULT '',
  "content_hash" varchar(64) NOT NULL DEFAULT '',
  "version" bigint NOT NULL DEFAULT 1,
  "draft_content" text,
  "draft_source_version" bigint NOT NULL DEFAULT 0,
  "draft_status" varchar(32) NOT NULL DEFAULT '',
  "draft_updated_at" timestamptz,
  "ext" json,
  "updated_by" varchar(255) NOT NULL DEFAULT '',
  "updated_by_name" varchar(255) NOT NULL DEFAULT '',
  "created_at" timestamptz NOT NULL,
  "updated_at" timestamptz NOT NULL,
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "skill_resources" (
  "id" varchar(36),
  "owner_user_id" varchar(255) NOT NULL,
  "owner_user_name" varchar(255) NOT NULL DEFAULT '',
  "category" varchar(128) NOT NULL,
  "parent_skill_name" varchar(255) NOT NULL DEFAULT '',
  "skill_name" varchar(255) NOT NULL DEFAULT '',
  "node_type" varchar(32) NOT NULL,
  "description" text,
  "tags" json,
  "file_ext" varchar(32) NOT NULL DEFAULT 'md',
  "relative_path" varchar(1024) NOT NULL,
  "storage_path" text NOT NULL DEFAULT '',
  "content_hash" varchar(64) NOT NULL DEFAULT '',
  "version" bigint NOT NULL DEFAULT 1,
  "draft_source_version" bigint NOT NULL DEFAULT 0,
  "draft_status" varchar(32) NOT NULL DEFAULT '',
  "draft_updated_at" timestamptz,
  "is_locked" boolean NOT NULL DEFAULT false,
  "is_enabled" boolean NOT NULL DEFAULT true,
  "update_status" varchar(32) NOT NULL DEFAULT 'up_to_date',
  "ext" json,
  "create_user_id" varchar(255) NOT NULL,
  "create_user_name" varchar(255) NOT NULL DEFAULT '',
  "created_at" timestamptz NOT NULL,
  "updated_at" timestamptz NOT NULL,
  PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX IF NOT EXISTS "uk_skill_resources_owner_relative_path" ON "skill_resources" ("owner_user_id","relative_path");
CREATE INDEX IF NOT EXISTS "idx_skill_resources_owner_node_enabled" ON "skill_resources" ("owner_user_id","node_type","is_enabled","category");

CREATE TABLE IF NOT EXISTS "resource_session_snapshots" (
  "id" varchar(36),
  "session_id" varchar(128) NOT NULL,
  "user_id" varchar(255) NOT NULL DEFAULT '',
  "resource_type" varchar(32) NOT NULL,
  "resource_key" varchar(1024) NOT NULL,
  "category" varchar(128) NOT NULL DEFAULT '',
  "parent_skill_name" varchar(255) NOT NULL DEFAULT '',
  "skill_name" varchar(255) NOT NULL DEFAULT '',
  "file_ext" varchar(32) NOT NULL DEFAULT '',
  "relative_path" varchar(1024) NOT NULL DEFAULT '',
  "snapshot_hash" varchar(64) NOT NULL DEFAULT '',
  "storage_path" text NOT NULL DEFAULT '',
  "created_at" timestamptz NOT NULL,
  PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX IF NOT EXISTS "uk_resource_session_snapshots" ON "resource_session_snapshots" ("session_id","resource_type","resource_key");
CREATE INDEX IF NOT EXISTS "idx_resource_session_snapshots_session_id" ON "resource_session_snapshots" ("session_id");

CREATE TABLE IF NOT EXISTS "resource_suggestions" (
  "id" varchar(36),
  "user_id" varchar(255) NOT NULL DEFAULT '',
  "resource_type" varchar(32) NOT NULL,
  "resource_key" varchar(1024) NOT NULL DEFAULT '',
  "category" varchar(128) NOT NULL DEFAULT '',
  "parent_skill_name" varchar(255) NOT NULL DEFAULT '',
  "skill_name" varchar(255) NOT NULL DEFAULT '',
  "file_ext" varchar(32) NOT NULL DEFAULT '',
  "relative_path" varchar(1024) NOT NULL DEFAULT '',
  "action" varchar(32) NOT NULL,
  "session_id" varchar(128) NOT NULL,
  "snapshot_hash" varchar(64) NOT NULL DEFAULT '',
  "title" varchar(255) NOT NULL DEFAULT '',
  "content" text,
  "reason" text,
  "full_content" text,
  "status" varchar(32) NOT NULL,
  "invalid_reason" text,
  "reviewer_id" varchar(255) NOT NULL DEFAULT '',
  "reviewer_name" varchar(255) NOT NULL DEFAULT '',
  "reviewed_at" timestamptz,
  "ext" json,
  "created_at" timestamptz NOT NULL,
  "updated_at" timestamptz NOT NULL,
  PRIMARY KEY ("id")
);
CREATE INDEX IF NOT EXISTS "idx_resource_suggestions_list" ON "resource_suggestions" ("user_id","resource_type","status");
CREATE INDEX IF NOT EXISTS "idx_resource_suggestions_session_id" ON "resource_suggestions" ("session_id");
