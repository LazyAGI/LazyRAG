import json
import os
import re
from utils.logger import log
from config import DATA_PATH
from typing import Dict, Any

from datetime import datetime
import uuid


def build_eval_report(eval_results, eval_data):
    total = len(eval_results)
    answer_correctness_list = []

    for item in eval_results:
        if "evaluate_result" in item:
            eval_result = item.pop("evaluate_result")
            item.update(eval_result)

            if "answer_correctness" in eval_result:
                try:
                    score = float(eval_result["answer_correctness"])
                    answer_correctness_list.append(score)
                except:
                    pass

    if answer_correctness_list:
        avg_score = round(sum(answer_correctness_list) / len(answer_correctness_list), 4)
    else:
        avg_score = 0.0

    return {
        "report_id": str(uuid.uuid4()),
        "eval_name": eval_data["eval_name"],
        "eval_set_id": eval_data.get("eval_set_id", ""),
        "kb_id": eval_data["kb_id"],
        "total": total,
        "avg_score": avg_score,
        "evaluate_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "details": eval_results
    }


def save_eval_report(eval_name, report):
    base_dir = f"{DATA_PATH}/datasets/{eval_name}"
    result_dir = os.path.join(base_dir, "results")
    os.makedirs(result_dir, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(result_dir, f"eval_report_{ts}.json")

    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return path


def ensure_eval_dir(eval_name: str):
    base = DATA_PATH + "/datasets"
    target = os.path.join(base, eval_name)
    os.makedirs(target, exist_ok=True)
    return target


def write_full_eval_set(eval_name: str, data: dict):
    folder = ensure_eval_dir(eval_name)
    file_path = os.path.join(folder, "eval_data.json")

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    log.info(f"评测集已保存至：{file_path}")
    return file_path


def extract_json(text: str) -> Dict:
    if isinstance(text, dict):
        return text
    try:
        return json.loads(text)
    except:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except:
                return {}
    return {}


def build_full_eval_set(
        qa_result: Any,
        eval_name: str,
        kb_id: str,
        task_id: str = ""
) -> Dict:
    cases = []
    for item in qa_result:
        try:
            qa = extract_json(item["qa"])
            case = {
                "case_id": str(uuid.uuid4()),
                "reference_doc": qa.get("reference_doc", "[]"),
                "reference_context": qa.get("reference_context", "[]"),
                "is_deleted": False,
                "question": qa.get("question", "1"),
                "question_type": qa.get("question_type", "1"),
                "key_points": qa.get("key_points", "[]"),
                "ground_truth": qa.get("ground_truth", ""),
                "generate_reason": qa.get("generate_reason", ""),
                "reference_chunk_ids": qa.get("reference_chunk_ids", []),
                "reference_doc_ids": qa.get("reference_doc_ids", []),
            }

            cases.append(case)
        except Exception:
            continue

    return {
        "eval_set_id": str(uuid.uuid4()),
        "eval_name": eval_name,
        "kb_id": kb_id,
        "task_id": task_id,
        "create_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_nums": len(cases),
        "cases": cases
    }
