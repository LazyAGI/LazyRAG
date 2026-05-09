-- +migrate Up

ALTER TABLE "user_model_provider_groups"
ADD COLUMN IF NOT EXISTS "is_verified" boolean NOT NULL DEFAULT false;
