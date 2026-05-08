-- +migrate Down

DROP INDEX IF EXISTS "idx_user_selected_models_user_id";
DROP INDEX IF EXISTS "uk_user_selected_models_user_type";
DROP TABLE IF EXISTS "user_selected_models";
