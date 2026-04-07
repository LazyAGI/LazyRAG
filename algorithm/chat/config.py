import os
from pathlib import Path
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
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHAT_DIR = PROJECT_ROOT / 'chat'

CONFIG_PATH = os.getenv("CONFIG_PATH", str(CHAT_DIR / "auto_model.yaml"))

USE_MULTIMODAL = False
LLM_TYPE_THINK = False

MAX_CONCURRENCY = int(os.getenv('MAX_CONCURRENCY', 10))
RAG_MODE = os.getenv('RAG_MODE', 'True').lower() == 'true'
MULTIMODAL_MODE = os.getenv('MULTIMODAL_MODE', 'True').lower() == 'true'

SENSITIVE_FILTER_RESPONSE_TEXT = '对不起，我还没有学会回答这个问题。如果你有其他问题，我非常乐意为你提供帮助。'

IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg')
DEFAULT_TMP_BLOCK_TOPK = 20

URL_MAP: Dict[str, str] = {
    'research_center': 'http://10.119.16.66:9003,research_center_0131_a',
    'quantum': 'http://10.119.16.66:9002,quantum_0131_a',
    'tyy': 'http://10.119.16.66:9007,tyy_0302',
    'cf': 'http://10.119.16.66:9005,cf_0304',
    '3m': 'http://10.119.16.66:9006,threem_0303',
    'crag': 'http://10.119.16.66:9001,crag_0130_a',
    'debug': 'http://127.0.0.1:8525',
}

DEFAULT_RETRIEVER_CONFIGS = [
    {
        'group_name': 'line',
        'embed_keys': ['bge_m3_dense'],
        'topk': 20,
        'target': 'block'
    },
    {
        'group_name': 'line',
        'embed_keys': ['bge_m3_sparse'],
        'topk': 20,
        'target': 'block'
    },
    {
        'group_name': 'block',
        'embed_keys': ['bge_m3_dense'],
        'topk': 20
    },
    {
        'group_name': 'block',
        'embed_keys': ['bge_m3_sparse'],
        'topk': 20
    },
]
