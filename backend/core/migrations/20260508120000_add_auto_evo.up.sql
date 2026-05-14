ALTER TABLE "skill_resources" RENAME COLUMN "is_locked" TO "auto_evo";
ALTER TABLE "skill_resources" ADD COLUMN "auto_evo_apply_status" varchar(32) NOT NULL DEFAULT 'idle';
ALTER TABLE "skill_resources" ADD COLUMN "auto_evo_generation" integer NOT NULL DEFAULT 0;
ALTER TABLE "skill_resources" ADD COLUMN "auto_evo_started_at" timestamptz;
ALTER TABLE "skill_resources" ADD COLUMN "auto_evo_finished_at" timestamptz;
ALTER TABLE "skill_resources" ADD COLUMN "auto_evo_error" text NOT NULL DEFAULT '';

ALTER TABLE "system_memories" ADD COLUMN "auto_evo" boolean NOT NULL DEFAULT true;
ALTER TABLE "system_memories" ADD COLUMN "auto_evo_apply_status" varchar(32) NOT NULL DEFAULT 'idle';
ALTER TABLE "system_memories" ADD COLUMN "auto_evo_generation" integer NOT NULL DEFAULT 0;
ALTER TABLE "system_memories" ADD COLUMN "auto_evo_started_at" timestamptz;
ALTER TABLE "system_memories" ADD COLUMN "auto_evo_finished_at" timestamptz;
ALTER TABLE "system_memories" ADD COLUMN "auto_evo_error" text NOT NULL DEFAULT '';

ALTER TABLE "system_user_preferences" ADD COLUMN "auto_evo" boolean NOT NULL DEFAULT true;
ALTER TABLE "system_user_preferences" ADD COLUMN "auto_evo_apply_status" varchar(32) NOT NULL DEFAULT 'idle';
ALTER TABLE "system_user_preferences" ADD COLUMN "auto_evo_generation" integer NOT NULL DEFAULT 0;
ALTER TABLE "system_user_preferences" ADD COLUMN "auto_evo_started_at" timestamptz;
ALTER TABLE "system_user_preferences" ADD COLUMN "auto_evo_finished_at" timestamptz;
ALTER TABLE "system_user_preferences" ADD COLUMN "auto_evo_error" text NOT NULL DEFAULT '';
