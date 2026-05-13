ALTER TABLE "system_user_preferences" DROP COLUMN "auto_evo_error";
ALTER TABLE "system_user_preferences" DROP COLUMN "auto_evo_finished_at";
ALTER TABLE "system_user_preferences" DROP COLUMN "auto_evo_started_at";
ALTER TABLE "system_user_preferences" DROP COLUMN "auto_evo_generation";
ALTER TABLE "system_user_preferences" DROP COLUMN "auto_evo_apply_status";
ALTER TABLE "system_user_preferences" DROP COLUMN "auto_evo";

ALTER TABLE "system_memories" DROP COLUMN "auto_evo_error";
ALTER TABLE "system_memories" DROP COLUMN "auto_evo_finished_at";
ALTER TABLE "system_memories" DROP COLUMN "auto_evo_started_at";
ALTER TABLE "system_memories" DROP COLUMN "auto_evo_generation";
ALTER TABLE "system_memories" DROP COLUMN "auto_evo_apply_status";
ALTER TABLE "system_memories" DROP COLUMN "auto_evo";

ALTER TABLE "skill_resources" DROP COLUMN "auto_evo_error";
ALTER TABLE "skill_resources" DROP COLUMN "auto_evo_finished_at";
ALTER TABLE "skill_resources" DROP COLUMN "auto_evo_started_at";
ALTER TABLE "skill_resources" DROP COLUMN "auto_evo_generation";
ALTER TABLE "skill_resources" DROP COLUMN "auto_evo_apply_status";
ALTER TABLE "skill_resources" RENAME COLUMN "auto_evo" TO "is_locked";
