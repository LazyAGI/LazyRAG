from lazyllm.configs import Config

# Single Config instance for the entire algorithm package.
# All LAZYRAG_* environment variables are registered here.
config = Config(prefix='LAZYRAG', home='~/.lazyllm_rag')

# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------
config.add('mount_base_dir', str, '/data', 'MOUNT_BASE_DIR', description='Base directory for mounted files.')
config.add('sensitive_words_path', str, 'data/sensitive_words.txt', 'SENSITIVE_WORDS_PATH', description='Path to sensitive words file.')
config.add('llm_priority', int, 0, 'LLM_PRIORITY', description='LLM priority level.')
config.add('max_concurrency', int, 10, 'MAX_CONCURRENCY', description='Max concurrent requests.')
config.add('rag_mode', bool, True, 'RAG_MODE', description='Enable RAG mode.')
config.add('multimodal_mode', bool, True, 'MULTIMODAL_MODE', description='Enable multimodal mode.')
config.add('algo_service_url', str, 'http://lazyllm-algo:8000', 'ALGO_SERVICE_URL', description='Algorithm service URL.')
config.add('algo_dataset_name', str, 'general_algo', 'ALGO_DATASET_NAME', description='Default algorithm dataset name.')
config.add('default_chat_dataset', str, 'algo', 'DEFAULT_CHAT_DATASET', description='Default chat dataset.')
config.add('skip_startup_pipeline', bool, False, 'SKIP_STARTUP_PIPELINE', description='Skip startup pipeline initialization.')
config.add('model_config_path', str, 'dynamic', 'MODEL_CONFIG_PATH', description='Runtime model config path (inner/online/dynamic or file path).')

# ---------------------------------------------------------------------------
# Tracing / observability
# ---------------------------------------------------------------------------
config.add('langfuse_force_flush_timeout_ms', int, 5000, 'LANGFUSE_FORCE_FLUSH_TIMEOUT_MS', description='Langfuse flush timeout in ms.')
config.add('local_trace_sink', bool, True, 'LOCAL_TRACE_SINK', description='Enable local in-memory trace sink.')
config.add('local_trace_max_traces', int, 512, 'LOCAL_TRACE_MAX_TRACES', description='Max traces kept in local sink.')
config.add('local_trace_ttl_s', int, 3600, 'LOCAL_TRACE_TTL_S', description='TTL in seconds for local trace entries.')
config.add('document_server_url', str, 'http://localhost:8000', 'DOCUMENT_SERVER_URL', description='Document server URL for health checks.')

# ---------------------------------------------------------------------------
# Agentic
# ---------------------------------------------------------------------------
config.add('agentic_kb_url', str, 'http://lazyllm-algo:8000', 'AGENTIC_KB_URL', description='Knowledge base service URL for agentic tools.')
config.add('core_api_url', str, 'http://core:8000', 'CORE_API_URL', description='Core API service URL.')
config.add('agentic_kb_name', str, 'general_algo', 'AGENTIC_KB_NAME', description='Default knowledge base name for agentic.')
config.add('skill_fs_url', str, 'remote://skills', 'SKILL_FS_URL', description='Skill filesystem URL.')
config.add('opensearch_uri', str, None, 'OPENSEARCH_URI', description='OpenSearch/Elasticsearch URI.')
config.add('opensearch_user', str, 'admin', 'OPENSEARCH_USER', description='OpenSearch username.')
config.add('opensearch_password', str, '', 'OPENSEARCH_PASSWORD', description='OpenSearch password.')
config.add('web_search_timeout', int, 10, 'WEB_SEARCH_TIMEOUT', description='Web search request timeout in seconds.')
config.add('web_search_auto_sources', str, 'bocha,google,bing,wikipedia', 'WEB_SEARCH_AUTO_SOURCES', description='Comma-separated list of auto web search sources.')
config.add('web_search_wikipedia_base_url', str, 'https://zh.wikipedia.org', 'WEB_SEARCH_WIKIPEDIA_BASE_URL', description='Wikipedia base URL for web search.')
config.add('web_search_google_api_key', str, '', 'WEB_SEARCH_GOOGLE_API_KEY', description='Google Custom Search API key.')
config.add('web_search_google_search_engine_id', str, '', 'WEB_SEARCH_GOOGLE_SEARCH_ENGINE_ID', description='Google Custom Search engine ID.')
config.add('web_search_bing_subscription_key', str, '', 'WEB_SEARCH_BING_SUBSCRIPTION_KEY', description='Bing Search subscription key.')
config.add('web_search_bing_endpoint', str, '', 'WEB_SEARCH_BING_ENDPOINT', description='Bing Search endpoint URL.')
config.add('web_search_bocha_api_key', str, '', 'WEB_SEARCH_BOCHA_API_KEY', description='Bocha search API key.')
config.add('web_search_bocha_base_url', str, 'https://api.bochaai.com', 'WEB_SEARCH_BOCHA_BASE_URL', description='Bocha search base URL.')
config.add('arxiv_search_timeout', int, 15, 'ARXIV_SEARCH_TIMEOUT', description='Arxiv search timeout in seconds.')
config.add('max_retries', int, 20, 'MAX_RETRIES', description='Max retries for agentic function call loop.')
config.add('memory_review_interval', int, 1, 'MEMORY_REVIEW_INTERVAL', description='Memory review trigger interval (turns).')
config.add('skill_review_interval', int, 5, 'SKILL_REVIEW_INTERVAL', description='Skill review trigger interval (turns).')
config.add('review_max_retries', int, 5, 'REVIEW_MAX_RETRIES', description='Max retries for background review agent.')
config.add('skill_review_debug', bool, False, 'SKILL_REVIEW_DEBUG', description='Enable skill review debug logging.')
config.add('review_debug', bool, False, 'REVIEW_DEBUG', description='Enable review debug logging.')

# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
config.add('milvus_uri', str, None, 'MILVUS_URI', description='Milvus vector store URI (required).')
config.add('ocr_server_type', str, 'none', 'OCR_SERVER_TYPE', description='OCR server type (none/mineru/paddleocr).')
config.add('ocr_server_url', str, 'http://localhost:8000', 'OCR_SERVER_URL', description='OCR server URL.')
config.add('mineru_upload_mode', str, None, 'MINERU_UPLOAD_MODE', description='MinerU upload mode override (auto-detected if unset).')
config.add('mineru_backend', str, 'pipeline', 'MINERU_BACKEND', description='MinerU processing backend.')
config.add('mineru_server_port', int, 8000, 'MINERU_SERVER_PORT', description='MinerU server port.')
config.add('mineru_cache_dir', str, None, 'MINERU_CACHE_DIR', description='MinerU cache directory.')
config.add('mineru_image_save_dir', str, None, 'MINERU_IMAGE_SAVE_DIR', description='MinerU image save directory.')
config.add('document_processor_url', str, 'http://localhost:8000', 'DOCUMENT_PROCESSOR_URL', description='Document processor service URL.')
config.add('algo_server_port', int, 8000, 'ALGO_SERVER_PORT', description='Algorithm server port.')
config.add('document_server_port', int, 8000, 'DOCUMENT_SERVER_PORT', description='Document server port (fallback for algo_server_port).')
config.add('startup_retry_interval', str, '2', 'STARTUP_RETRY_INTERVAL', description='Startup retry interval in seconds.')
config.add('startup_timeout', str, '0', 'STARTUP_TIMEOUT', description='Startup wait timeout in seconds (0 = no timeout).')
config.add('rag_image_path_prefix', str, '/mnt/lustre/share_data/mineru/images/', 'RAG_IMAGE_PATH_PREFIX', description='Image path prefix for RAG documents.')

# ---------------------------------------------------------------------------
# Processor
# ---------------------------------------------------------------------------
config.add('database_url', str, None, 'DATABASE_URL', description='Shared PostgreSQL URL (required for document processor).')
config.add('document_worker_port', int, 8001, 'DOCUMENT_WORKER_PORT', description='Document processor worker port.')
config.add('document_worker_num_workers', int, 1, 'DOCUMENT_WORKER_NUM_WORKERS', description='Number of document processor workers.')
# float values stored as str; consumers call float(config['...'])
config.add('document_worker_lease_duration', str, '300.0', 'DOCUMENT_WORKER_LEASE_DURATION', description='Worker lease duration in seconds.')
config.add('document_worker_lease_renew_interval', str, '60.0', 'DOCUMENT_WORKER_LEASE_RENEW_INTERVAL', description='Worker lease renew interval in seconds.')
config.add('document_worker_high_priority_task_types', str, None, 'DOCUMENT_WORKER_HIGH_PRIORITY_TASK_TYPES', description='Comma-separated high-priority task types.')
config.add('document_worker_high_priority_only', bool, False, 'DOCUMENT_WORKER_HIGH_PRIORITY_ONLY', description='Process only high-priority tasks.')
config.add('document_worker_poll_mode', str, 'direct', 'DOCUMENT_WORKER_POLL_MODE', description='Worker poll mode.')
config.add('upload_dir', str, '/app/uploads', 'UPLOAD_DIR', description='Upload directory for document files.')
config.add('default_algo_id', str, 'general_algo', 'DEFAULT_ALGO_ID', description='Default algorithm ID for uploads.')
config.add('default_group', str, 'block', 'DEFAULT_GROUP', description='Default group name for uploads.')
config.add('document_processor_port', int, 8000, 'DOCUMENT_PROCESSOR_PORT', description='Document processor HTTP port.')
config.add('upload_server_port', int, 8001, 'UPLOAD_SERVER_PORT', description='Upload server port.')

# ---------------------------------------------------------------------------
# Vocab
# ---------------------------------------------------------------------------
config.add('core_database_url', str, None, 'CORE_DATABASE_URL', description='Core service PostgreSQL URL.')
config.add('word_group_apply_url', str, None, 'WORD_GROUP_APPLY_URL', description='Word group apply endpoint URL.')
config.add('core_service_url', str, None, 'CORE_SERVICE_URL', description='Core service base URL.')
# ACL_DB_DSN: now requires LAZYRAG_ACL_DB_DSN prefix.
config.add('acl_db_dsn', str, None, 'ACL_DB_DSN', description='ACL database DSN (PostgreSQL connection string).')
