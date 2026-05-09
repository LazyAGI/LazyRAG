-- +migrate Down

ALTER TABLE "user_model_provider_groups"
DROP COLUMN IF EXISTS "is_verified";
