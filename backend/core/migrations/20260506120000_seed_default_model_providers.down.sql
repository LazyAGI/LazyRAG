-- +migrate Down

DELETE FROM "default_model_providers" WHERE "name" IN ('Claude', 'DeepSeek', 'Doubao', 'GLM', 'Kimi', 'Minimax', 'OpenAI', 'Qwen', 'SenseNova', 'SiliconFlow');
