-- +migrate Up
-- word_group_conflicts: no action column; soft delete via deleted_at (aligned with orm.WordGroupConflict).

CREATE TABLE IF NOT EXISTS word_group_conflicts (
  id varchar(64) PRIMARY KEY,
  reason text NOT NULL DEFAULT '',
  word text NOT NULL DEFAULT '',
  description text NOT NULL DEFAULT '',
  group_ids text NOT NULL DEFAULT '[]',
  create_user_id varchar(255) NOT NULL,
  message_ids text NOT NULL DEFAULT '[]',
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  deleted_at timestamptz
);

-- Optimized for: WHERE create_user_id = ? AND deleted_at IS NULL ORDER BY updated_at DESC.
-- Partial index keeps it lean by skipping soft-deleted rows; composite covers filter + sort.
CREATE INDEX IF NOT EXISTS idx_word_group_conflict_user_updated
  ON word_group_conflicts (create_user_id, updated_at DESC)
  WHERE deleted_at IS NULL;
