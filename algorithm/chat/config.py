from typing import Dict

from dotenv import load_dotenv

from config import config

load_dotenv()

MOUNT_BASE_DIR: str = config['mount_base_dir']
SENSITIVE_WORDS_PATH: str = config['sensitive_words_path']

LAZYRAG_LLM_PRIORITY: int = config['llm_priority']
USE_MULTIMODAL = False
LLM_TYPE_THINK = False

MAX_CONCURRENCY: int = config['max_concurrency']
RAG_MODE: bool = config['rag_mode']
MULTIMODAL_MODE: bool = config['multimodal_mode']

SENSITIVE_FILTER_RESPONSE_TEXT = 'Sorry, I have not learned how to answer this question yet. If you have other questions, I am happy to help.'  # noqa: E501

IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg')
DEFAULT_TMP_BLOCK_TOPK = 20

DEFAULT_ALGO_SERVICE_URL: str = config['algo_service_url'].rstrip('/')
DEFAULT_ALGO_DATASET_NAME: str = config['algo_dataset_name']
DEFAULT_CHAT_DATASET: str = config['default_chat_dataset']

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


def resolve_dataset_url(dataset: str | None) -> str | None:
    if not dataset:
        return None
    if dataset in URL_MAP:
        return URL_MAP[dataset]
    if dataset.startswith('ds_'):
        return f'{DEFAULT_ALGO_SERVICE_URL},{dataset}'
    return None
