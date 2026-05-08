-- +migrate Up

-- Built-in model provider catalog and per-user copies (final schema).

CREATE TABLE IF NOT EXISTS "default_model_providers" (
  "id" varchar(64) PRIMARY KEY,
  "name" varchar(255) NOT NULL,
  "description" text NOT NULL,
  "base_url" varchar(1024) NOT NULL DEFAULT '',
  "created_at" timestamptz NOT NULL,
  "updated_at" timestamptz NOT NULL,
  "deleted_at" timestamptz
);

CREATE UNIQUE INDEX IF NOT EXISTS "uk_default_model_providers_name" ON "default_model_providers" ("name");

CREATE TABLE IF NOT EXISTS "user_model_providers" (
  "id" varchar(64) PRIMARY KEY,
  "default_model_provider_id" varchar(64) NOT NULL,
  "name" varchar(255) NOT NULL,
  "description" text NOT NULL,
  "base_url" varchar(1024) NOT NULL DEFAULT '',
  "create_user_id" varchar(255) NOT NULL,
  "create_user_name" varchar(255) NOT NULL,
  "created_at" timestamptz NOT NULL,
  "updated_at" timestamptz NOT NULL,
  "deleted_at" timestamptz
);

CREATE UNIQUE INDEX IF NOT EXISTS "uk_user_model_providers_user_default_provider" ON "user_model_providers" ("create_user_id", "default_model_provider_id");
CREATE INDEX IF NOT EXISTS "idx_user_model_providers_create_user_id" ON "user_model_providers" ("create_user_id");
