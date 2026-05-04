ALTER TABLE "system_memories" ADD COLUMN "user_id" varchar(255) NOT NULL DEFAULT '';
ALTER TABLE "system_user_preferences" ADD COLUMN "user_id" varchar(255) NOT NULL DEFAULT '';

UPDATE "system_memories"
SET "user_id" = "updated_by"
WHERE "user_id" = '' AND "updated_by" <> '' AND "updated_by" <> 'system';

UPDATE "system_user_preferences"
SET "user_id" = "updated_by"
WHERE "user_id" = '' AND "updated_by" <> '' AND "updated_by" <> 'system';

CREATE UNIQUE INDEX IF NOT EXISTS "uk_system_memories_user_id" ON "system_memories" ("user_id");
CREATE UNIQUE INDEX IF NOT EXISTS "uk_system_user_preferences_user_id" ON "system_user_preferences" ("user_id");
