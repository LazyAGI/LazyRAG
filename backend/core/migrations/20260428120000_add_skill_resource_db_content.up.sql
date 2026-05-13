ALTER TABLE "skill_resources" ADD COLUMN "content" text NOT NULL DEFAULT '';
ALTER TABLE "skill_resources" ADD COLUMN "content_size" bigint NOT NULL DEFAULT 0;
ALTER TABLE "skill_resources" ADD COLUMN "mime_type" varchar(128) NOT NULL DEFAULT 'text/plain; charset=utf-8';
ALTER TABLE "skill_resources" ADD COLUMN "draft_content" text NOT NULL DEFAULT '';
