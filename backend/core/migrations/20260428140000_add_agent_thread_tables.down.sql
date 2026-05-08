DROP INDEX IF EXISTS "idx_agent_thread_records_round_stream_id";
DROP INDEX IF EXISTS "idx_agent_thread_records_thread_round_id";
DROP INDEX IF EXISTS "idx_agent_thread_records_thread_stream_id";
DROP INDEX IF EXISTS "uk_agent_thread_records_record_key";
DROP TABLE IF EXISTS "agent_thread_records";

DROP INDEX IF EXISTS "idx_agent_thread_rounds_thread_request_hash";
DROP INDEX IF EXISTS "idx_agent_thread_rounds_thread_id";
DROP TABLE IF EXISTS "agent_thread_rounds";

DROP INDEX IF EXISTS "idx_agent_threads_current_task_id";
DROP TABLE IF EXISTS "agent_threads";
