-- +migrate Up

-- Per-user model rows under a connection group (seeded from default_models when base_url matches catalog).
-- provider_name denormalizes user_model_providers.name. Group title comes from user_model_provider_groups join.

CREATE TABLE IF NOT EXISTS "user_model_provider_group_models" (
  "id" varchar(64) PRIMARY KEY,
  "user_model_provider_id" varchar(64) NOT NULL,
  "user_model_provider_group_id" varchar(64) NOT NULL,
  "provider_name" varchar(255) NOT NULL DEFAULT '',
  "name" varchar(512) NOT NULL,
  "model_type" varchar(64) NOT NULL,
  "base_url" varchar(1024) NOT NULL DEFAULT '',
  "is_default" boolean NOT NULL DEFAULT false,
  "create_user_id" varchar(255) NOT NULL,
  "create_user_name" varchar(255) NOT NULL,
  "created_at" timestamptz NOT NULL,
  "updated_at" timestamptz NOT NULL,
  "deleted_at" timestamptz
);

CREATE UNIQUE INDEX IF NOT EXISTS "uk_user_model_provider_group_models_group_name" ON "user_model_provider_group_models" ("user_model_provider_group_id", "name");
CREATE INDEX IF NOT EXISTS "idx_user_model_provider_group_models_provider" ON "user_model_provider_group_models" ("user_model_provider_id");
CREATE INDEX IF NOT EXISTS "idx_user_model_provider_group_models_create_user_id" ON "user_model_provider_group_models" ("create_user_id");
