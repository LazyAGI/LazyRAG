import os
from typing import Dict

from dotenv import load_dotenv

load_dotenv()

MOUNT_BASE_DIR: str = os.getenv('LAZYLLM_MOUNT_DIR', '/data')
SENSITIVE_WORDS_PATH: str = os.getenv('SENSITIVE_WORDS_PATH', 'data/sensitive_words.txt')

_LAZYRAG_LLM_PRIORITY_ENV = os.getenv('LAZYRAG_LLM_PRIORITY')
LAZYRAG_LLM_PRIORITY = (
    int(_LAZYRAG_LLM_PRIORITY_ENV)
    if _LAZYRAG_LLM_PRIORITY_ENV is not None and _LAZYRAG_LLM_PRIORITY_ENV.isdigit()
    else 0
)
USE_MULTIMODAL = False
LLM_TYPE_THINK = False

MAX_CONCURRENCY = int(os.getenv('LAZYRAG_MAX_CONCURRENCY', 10))
RAG_MODE = os.getenv('RAG_MODE', 'True').lower() == 'true'
MULTIMODAL_MODE = os.getenv('MULTIMODAL_MODE', 'True').lower() == 'true'

SENSITIVE_FILTER_RESPONSE_TEXT = '对不起，我还没有学会回答这个问题。如果你有其他问题，我非常乐意为你提供帮助。'

IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg')
DEFAULT_TMP_BLOCK_TOPK = 20

DEFAULT_ALGO_SERVICE_URL = os.getenv('LAZYRAG_ALGO_SERVICE_URL', 'http://lazyllm-algo:8000').rstrip('/')
DEFAULT_ALGO_DATASET_NAME = os.getenv('LAZYRAG_ALGO_DATASET_NAME', 'general_algo')
DEFAULT_CHAT_DATASET = os.getenv('LAZYRAG_DEFAULT_CHAT_DATASET', 'algo')

URL_MAP: Dict[str, str] = {
    'algo': f'{DEFAULT_ALGO_SERVICE_URL},{DEFAULT_ALGO_DATASET_NAME}',
    'default': f'{DEFAULT_ALGO_SERVICE_URL},{DEFAULT_ALGO_DATASET_NAME}',
    'general_algo': f'{DEFAULT_ALGO_SERVICE_URL},{DEFAULT_ALGO_DATASET_NAME}',
    'research_center': 'http://10.119.16.66:9003,research_center_0131_a',
    'quantum': 'http://10.119.16.66:9002,quantum_0131_a',
    # 'tyy': 'http://10.119.16.66:9007,tyy_0302',
    'cf': 'http://10.119.16.66:9005,cf_0304',
    '3m': 'http://10.119.16.66:9006,threem_0303',
    'crag': 'http://10.119.16.66:9001,crag_0130_a',
    'debug': 'http://127.0.0.1:8525',
    'tyy': 'http://10.119.24.129:8056,general_algo',
}
