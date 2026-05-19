-- 20260518120000_add_skill_source_type
-- +migrate Up

ALTER TABLE "skill_resources" ADD COLUMN "source_type" varchar(32) NOT NULL DEFAULT 'user';
CREATE INDEX IF NOT EXISTS "idx_skill_resources_source_type" ON "skill_resources" ("source_type");
