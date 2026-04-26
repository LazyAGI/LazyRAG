import requests
from config import DOC_API, REQUEST_TIMEOUT, CHUNK_API
from utils.logger import log

def get_doc_list(kb_id, algo_id="general_algo"):
    try:
        doc_res = requests.get(
            DOC_API,
            params={"kb_id": kb_id, "algo_id": algo_id},
            timeout=REQUEST_TIMEOUT  # 超时控制
        )
        return doc_res.json()["data"]["items"]
    except requests.exceptions.Timeout:
        log.info(f"获取文档列表超时（{REQUEST_TIMEOUT}秒）")
        return []
    except Exception as e:
        log.info("获取文档列表错误:", e)
        return []

def get_all_chunks_with_docid(kb_id, doc_id, algo_id="general_algo"):
    chunks = []
    try:
        res = requests.get(CHUNK_API, params={
            "kb_id": kb_id, "doc_id": doc_id, "group": "block", "algo_id": algo_id
        }, timeout=REQUEST_TIMEOUT)
        items = res.json().get("data", {}).get("items", [])
        for it in items:
            content = it.get("content", "").strip()
            file_name = it.get("metadata", {}).get("file_name", "unknown")
            chunk_uid = it.get("uid", "")
            chunk_doc_id = it.get("doc_id", doc_id)
            if content:
                chunks.append({
                    "content": content,
                    "filename": file_name,
                    "chunk_id": chunk_uid,
                    "doc_id": chunk_doc_id
                })
    except Exception as e:
        log.info(f"⚠️ 获取分片异常: {e}")
    return chunks


