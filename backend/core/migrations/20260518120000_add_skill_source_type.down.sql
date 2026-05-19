-- 20260518120000_add_skill_source_type
-- +migrate Down

DROP INDEX IF EXISTS "idx_skill_resources_source_type";
ALTER TABLE "skill_resources" DROP COLUMN "source_type";
