-- +migrate Down

DROP INDEX IF EXISTS idx_word_create_user_group_id;
DROP INDEX IF EXISTS idx_word_column;

CREATE INDEX IF NOT EXISTS idx_word_group_word_kind ON words (group_id, word, word_kind);
CREATE INDEX IF NOT EXISTS idx_word_column ON words (word);
CREATE INDEX IF NOT EXISTS idx_word_create_user_id ON words (create_user_id);
