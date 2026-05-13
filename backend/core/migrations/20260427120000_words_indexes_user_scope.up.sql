-- +migrate Up

-- Drop all indexes created by 20260423120000_create_word.up.sql (lines 18-20).
DROP INDEX IF EXISTS idx_word_group_word_kind;
DROP INDEX IF EXISTS idx_word_column;
DROP INDEX IF EXISTS idx_word_create_user_id;

-- Idempotent: drop targets before create (partial runs / same name as legacy idx_word_column).
DROP INDEX IF EXISTS idx_word_create_user_group_id;
DROP INDEX IF EXISTS idx_word_column;

CREATE INDEX IF NOT EXISTS idx_word_create_user_group_id ON words (create_user_id, group_id);
CREATE INDEX IF NOT EXISTS idx_word_column ON words (create_user_id, word);
