-- 20260315095955_init
-- +migrate Up

CREATE TABLE "acl_visibility" ("id" bigserial,"resource_id" varchar(255),"level" varchar(32),PRIMARY KEY ("id"));
CREATE INDEX IF NOT EXISTS "idx_acl_visibility_resource_id" ON "acl_visibility" ("resource_id");
CREATE TABLE "acl_rows" ("id" bigserial,"resource_type" varchar(32),"resource_id" varchar(255),"grantee_type" varchar(32),"target_id" bigint,"permission" varchar(32),"created_by" bigint,"created_at" timestamptz,"expires_at" timestamptz,PRIMARY KEY ("id"));
CREATE INDEX IF NOT EXISTS "idx_acl_resource" ON "acl_rows" ("resource_type","resource_id");
CREATE TABLE "acl_kbs" ("id" varchar(64),"name" varchar(255),"owner_id" bigint,"visibility" varchar(32),PRIMARY KEY ("id"));
CREATE TABLE "acl_user_groups" ("user_id" bigint,"group_id" bigint,PRIMARY KEY ("user_id","group_id"));
CREATE TABLE "prompts" ("id" varchar(64),"name" varchar(255) NOT NULL,"content" text NOT NULL,"create_user_id" varchar(255) NOT NULL,"create_user_name" varchar(255) NOT NULL,"created_at" timestamptz NOT NULL,"updated_at" timestamptz NOT NULL,"deleted_at" timestamptz,PRIMARY KEY ("id"));
CREATE UNIQUE INDEX IF NOT EXISTS "idx_prompts_name" ON "prompts" ("name");
CREATE TABLE "default_prompts" ("id" bigserial,"prompt_id" varchar(64) NOT NULL,"prompt_name" varchar(255) NOT NULL,"create_user_id" varchar(255) NOT NULL,"create_user_name" varchar(255) NOT NULL,"created_at" timestamptz NOT NULL,"updated_at" timestamptz NOT NULL,"deleted_at" timestamptz,PRIMARY KEY ("id"));
CREATE TABLE "multi_answers_switches" ("id" serial,"status" integer NOT NULL DEFAULT 0,"create_user_id" varchar(255) NOT NULL,"create_user_name" varchar(255) NOT NULL,"created_at" timestamptz NOT NULL,"updated_at" timestamptz NOT NULL,"deleted_at" timestamptz,PRIMARY KEY ("id"));
CREATE TABLE "conversations" ("id" varchar(36),"display_name" varchar(255),"channel_id" varchar(36) NOT NULL DEFAULT 'default',"search_config" json,"application_id" varchar(64) DEFAULT '',"ext" json,"model" varchar(64) DEFAULT '',"models" json,"chat_times" integer NOT NULL DEFAULT 0,"create_user_id" varchar(255) NOT NULL,"create_user_name" varchar(255) NOT NULL,"created_at" timestamptz NOT NULL,"updated_at" timestamptz NOT NULL,"deleted_at" timestamptz,PRIMARY KEY ("id"));
CREATE TABLE "chat_histories" ("id" varchar(36),"seq" bigint NOT NULL,"conversation_id" varchar(36) NOT NULL,"raw_content" text,"retrieval_result" json,"content" text,"result" text,"feed_back" bigint DEFAULT 0,"reason" varchar(255),"expected_answer" text,"ext" json,"version" varchar(128) DEFAULT '2.3',"create_time" timestamptz NOT NULL,"update_time" timestamptz NOT NULL,PRIMARY KEY ("id"));
CREATE INDEX IF NOT EXISTS "idx_chat_histories_conversation_id" ON "chat_histories" ("conversation_id");
CREATE TABLE "multi_answers_chat_histories" ("id" varchar(36),"seq" bigint NOT NULL,"conversation_id" varchar(36) NOT NULL,"raw_content" text,"retrieval_result" json,"content" text,"result" text,"feed_back" bigint DEFAULT 0,"reason" varchar(255),"ext" json,"endpoint" varchar(512),"create_time" timestamptz NOT NULL,"update_time" timestamptz NOT NULL,PRIMARY KEY ("id"));
CREATE INDEX IF NOT EXISTS "idx_multi_answers_chat_histories_conversation_id" ON "multi_answers_chat_histories" ("conversation_id");
