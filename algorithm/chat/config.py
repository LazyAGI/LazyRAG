import json
from typing import Dict

from dotenv import load_dotenv
from config import config

load_dotenv()

MOUNT_BASE_DIR: str = config['mount_base_dir']
SENSITIVE_WORDS_PATH: str = config['sensitive_words_path']

LAZYMIND_LLM_PRIORITY: int = config['llm_priority']

MAX_CONCURRENCY: int = config['max_concurrency']
RAG_MODE: bool = config['rag_mode']
MULTIMODAL_MODE: bool = config['multimodal_mode']

SENSITIVE_FILTER_RESPONSE_TEXT = 'Sorry, I have not learned how to answer this question yet. If you have other questions, I am happy to help.'  # noqa: E501

IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg')
DEFAULT_TMP_BLOCK_TOPK = 20

DEFAULT_ALGO_SERVICE_URL: str = config['algo_service_url'].rstrip('/')
DEFAULT_ALGO_DATASET_NAME: str = config['algo_dataset_name']
DEFAULT_CHAT_DATASET: str = config['default_chat_dataset']

_DEFAULT_URL_MAP: Dict[str, str] = {
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


def _parse_dataset_url_map(raw: str) -> Dict[str, str]:
    text = str(raw or '').strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    result: Dict[str, str] = {}
    for key, value in parsed.items():
        if not isinstance(key, str):
            continue
        normalized_key = key.strip()
        normalized_value = str(value or '').strip()
        if normalized_key and normalized_value:
            result[normalized_key] = normalized_value
    return result


URL_MAP: Dict[str, str] = {
    **_DEFAULT_URL_MAP,
    **_parse_dataset_url_map(config['dataset_url_map']),
}


def resolve_dataset_binding(dataset: str | None) -> tuple[str | None, str | None]:
    if not dataset:
        return None, None
    if dataset in URL_MAP:
        raw = URL_MAP[dataset]
    elif dataset.startswith('ds_'):
        raw = f'{DEFAULT_ALGO_SERVICE_URL},{dataset}'
    else:
        return None, None

    parts = [part.strip() for part in str(raw).split(',', 1)]
    kb_url = parts[0] if parts and parts[0] else None
    kb_name = parts[1] if len(parts) > 1 and parts[1] else None
    return kb_url, kb_name
