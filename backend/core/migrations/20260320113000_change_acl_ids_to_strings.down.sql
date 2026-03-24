-- 20260320113000_change_acl_ids_to_strings
-- +migrate Down

ALTER TABLE "acl_user_groups"
  ALTER COLUMN "user_id" TYPE bigint USING NULLIF("user_id", '')::bigint,
  ALTER COLUMN "group_id" TYPE bigint USING NULLIF("group_id", '')::bigint;

ALTER TABLE "acl_kbs"
  ALTER COLUMN "owner_id" TYPE bigint USING NULLIF("owner_id", '')::bigint;

ALTER TABLE "acl_rows"
  ALTER COLUMN "target_id" TYPE bigint USING NULLIF("target_id", '')::bigint,
  ALTER COLUMN "created_by" TYPE bigint USING NULLIF("created_by", '')::bigint;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = current_schema()
      AND table_name = 'acl_groups'
      AND column_name = 'id'
      AND data_type = 'character varying'
  ) THEN
    ALTER TABLE "acl_groups"
      ALTER COLUMN "id" TYPE bigint USING NULLIF("id", '')::bigint;
  END IF;
END $$;
