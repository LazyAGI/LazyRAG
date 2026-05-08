-- +migrate Down

DROP INDEX IF EXISTS idx_word_group_conflict_user_updated;
DROP TABLE IF EXISTS word_group_conflicts;
