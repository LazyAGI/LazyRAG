-- +migrate Up

-- Built-in model catalog: name, model_type, default_model_provider_id, provider_name (denormalized), base_url, timestamps.

CREATE TABLE IF NOT EXISTS "default_models" (
  "id" varchar(64) PRIMARY KEY,
  "default_model_provider_id" varchar(64) NOT NULL,
  "provider_name" varchar(255) NOT NULL DEFAULT '',
  "name" varchar(512) NOT NULL,
  "model_type" varchar(64) NOT NULL,
  "base_url" varchar(1024) NOT NULL DEFAULT '',
  "created_at" timestamptz NOT NULL,
  "updated_at" timestamptz NOT NULL,
  "deleted_at" timestamptz
);

CREATE UNIQUE INDEX IF NOT EXISTS "uk_default_models_provider_name" ON "default_models" ("default_model_provider_id", "name");
