import os

HOST = "0.0.0.0"
PORT = 39800

# 从环境变量获取 LLM 配置（如果环境变量没有，提示配置）
LLM_API_KEY = os.environ["LLM_API_KEY"]
LLM_BASE_URL = os.environ["LLM_BASE_URL"]
LLM_MODEL = os.environ["LLM_MODEL"]

CHUNK_HOST = "http://localhost:8055"
DOC_API = CHUNK_HOST + "/v1/docs"
CHUNK_API = CHUNK_HOST + "/v1/chunks"

CHAT_API = "http://localhost:8055/api/chat"

MAX_PROCESS_CHUNK_PER_DOC = 200
MAX_WORKERS = 10

REQUEST_TIMEOUT = 10

DATA_PATH = "./data"

# 评测集数量配置
TASK_SETTINGS = {
    "single_hop": {"num": 1},
    "multi_hop": {"num": 20},
    "multi_file": {"num": 20},
    "formula": {"num": 5},
    "table": {"num": 5},
}
