-- 20260317120000_add_datasets_tables_and_kb_id
-- +migrate Down

DROP TABLE IF EXISTS default_datasets CASCADE;
DROP TABLE IF EXISTS dataset_members CASCADE;
DROP TABLE IF EXISTS datasets CASCADE;

