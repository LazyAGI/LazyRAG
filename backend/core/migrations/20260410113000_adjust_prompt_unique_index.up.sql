-- Change prompt name uniqueness from global to per-user.
DROP INDEX IF EXISTS idx_prompts_name;
CREATE UNIQUE INDEX IF NOT EXISTS uk_prompts_user_name ON prompts (create_user_id, name);
