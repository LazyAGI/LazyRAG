-- +migrate Up

CREATE TABLE IF NOT EXISTS "user_selected_models" (
  "id" bigserial PRIMARY KEY,
  "user_id" varchar(255) NOT NULL,
  "user_name" varchar(255) NOT NULL DEFAULT '',
  "model_type" varchar(64) NOT NULL,
  "user_model_provider_group_model_id" varchar(64) NOT NULL,
  "created_at" timestamptz NOT NULL,
  "updated_at" timestamptz NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS "uk_user_selected_models_user_type" ON "user_selected_models" ("user_id", "model_type");
CREATE INDEX IF NOT EXISTS "idx_user_selected_models_user_id" ON "user_selected_models" ("user_id");
