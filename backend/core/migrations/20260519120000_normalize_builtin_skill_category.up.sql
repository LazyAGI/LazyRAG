-- 20260519120000_normalize_builtin_skill_category
-- +migrate Up

UPDATE "skill_resources"
SET
  "category" = 'build-in',
  "relative_path" = CASE
    WHEN "node_type" = 'parent'
      THEN 'build-in/' || "skill_name" || '/SKILL.md'
    ELSE 'build-in/' || "parent_skill_name" || '/' ||
      regexp_replace("relative_path", '^([^/]+)/([^/]+)/', '')
  END,
  "description" = COALESCE("description", '')
WHERE "owner_user_id" = '__builtin__'
  AND "category" <> 'build-in';
