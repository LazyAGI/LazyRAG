-- 20260317120000_add_datasets_tables_and_kb_id
-- +migrate Up

-- Dataset tables (created for DatasetService endpoints)

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

