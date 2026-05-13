CREATE TABLE IF NOT EXISTS "user_personalization_settings" (
  "id" bigserial,
  "user_id" varchar(255) NOT NULL,
  "enabled" boolean NOT NULL DEFAULT true,
  "updated_by" varchar(255) NOT NULL DEFAULT '',
  "updated_by_name" varchar(255) NOT NULL DEFAULT '',
  "created_at" timestamptz NOT NULL,
  "updated_at" timestamptz NOT NULL,
  PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX IF NOT EXISTS "uk_user_personalization_settings_user_id" ON "user_personalization_settings" ("user_id");
