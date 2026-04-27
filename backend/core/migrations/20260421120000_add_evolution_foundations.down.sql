DROP INDEX IF EXISTS idx_resource_suggestions_session_id;
DROP INDEX IF EXISTS idx_resource_suggestions_list;
DROP TABLE IF EXISTS resource_suggestions;

DROP INDEX IF EXISTS idx_resource_session_snapshots_session_id;
DROP INDEX IF EXISTS uk_resource_session_snapshots;
DROP TABLE IF EXISTS resource_session_snapshots;

DROP INDEX IF EXISTS idx_skill_resources_owner_node_enabled;
DROP INDEX IF EXISTS uk_skill_resources_owner_relative_path;
DROP TABLE IF EXISTS skill_resources;

DROP TABLE IF EXISTS system_user_preferences;
DROP TABLE IF EXISTS system_memories;
