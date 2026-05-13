-- +migrate Up

CREATE TABLE IF NOT EXISTS "user_model_provider_groups" (
  "id" varchar(64) PRIMARY KEY,
  "user_model_provider_id" varchar(64) NOT NULL,
  "name" varchar(255) NOT NULL,
  "base_url" varchar(1024) NOT NULL,
  "api_key" text NOT NULL,
  "create_user_id" varchar(255) NOT NULL,
  "create_user_name" varchar(255) NOT NULL,
  "created_at" timestamptz NOT NULL,
  "updated_at" timestamptz NOT NULL,
  "deleted_at" timestamptz
);

CREATE INDEX IF NOT EXISTS "idx_user_model_provider_groups_parent" ON "user_model_provider_groups" ("user_model_provider_id");
CREATE INDEX IF NOT EXISTS "idx_user_model_provider_groups_create_user_id" ON "user_model_provider_groups" ("create_user_id");
