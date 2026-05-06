-- +migrate Up

CREATE TABLE IF NOT EXISTS words (
  id varchar(64) PRIMARY KEY,
  word varchar(512) NOT NULL,
  group_id varchar(64) NOT NULL,
  description varchar(512) NOT NULL DEFAULT '',
  source varchar(32) NOT NULL DEFAULT 'user',
  reference_info text NOT NULL DEFAULT '',
  locked boolean NOT NULL DEFAULT false,
  word_kind varchar(32) NOT NULL DEFAULT 'term',
  create_user_id varchar(255) NOT NULL,
  create_user_name varchar(255) NOT NULL,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  deleted_at timestamptz
);
CREATE INDEX IF NOT EXISTS idx_word_group_word_kind ON words (group_id, word, word_kind);
CREATE INDEX IF NOT EXISTS idx_word_column ON words (word);
CREATE INDEX IF NOT EXISTS idx_word_create_user_id ON words (create_user_id);
