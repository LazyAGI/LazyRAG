-- 20260320113000_change_acl_ids_to_strings
-- +migrate Up

CREATE TABLE IF NOT EXISTS "acl_groups" (
  "id" varchar(255),
  "name" varchar(255) NOT NULL DEFAULT '',
  PRIMARY KEY ("id")
);

ALTER TABLE "acl_rows"
  ALTER COLUMN "target_id" TYPE varchar(255) USING "target_id"::varchar,
  ALTER COLUMN "created_by" TYPE varchar(255) USING "created_by"::varchar;

ALTER TABLE "acl_kbs"
  ALTER COLUMN "owner_id" TYPE varchar(255) USING "owner_id"::varchar;

ALTER TABLE "acl_user_groups"
  ALTER COLUMN "user_id" TYPE varchar(255) USING "user_id"::varchar,
  ALTER COLUMN "group_id" TYPE varchar(255) USING "group_id"::varchar;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = current_schema()
      AND table_name = 'acl_groups'
      AND column_name = 'id'
      AND data_type <> 'character varying'
  ) THEN
    ALTER TABLE "acl_groups"
      ALTER COLUMN "id" TYPE varchar(255) USING "id"::varchar;
  END IF;
END $$;
