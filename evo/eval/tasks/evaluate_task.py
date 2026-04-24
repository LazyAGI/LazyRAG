import uuid
import json
import os
from fastapi import BackgroundTasks
from pipelines.evaluate_pipeline import run_evaluate_pipeline
from utils.writer import build_eval_report, save_eval_report
from config import DATA_PATH

# ============================
# 任务持久化
# ============================
TASK_STORE_PATH = DATA_PATH + "/tasks/evaluate_tasks.json"

# 启动时加载历史任务
if os.path.exists(TASK_STORE_PATH):
    with open(TASK_STORE_PATH, "r", encoding="utf-8") as f:
        eval_tasks = json.load(f)
else:
    eval_tasks = {}


# 保存任务到文件
def save_eval_tasks():
    with open(TASK_STORE_PATH, "w", encoding="utf-8") as f:
        json.dump(eval_tasks, f, ensure_ascii=False, indent=2)


def create_evaluate_task(background_tasks: BackgroundTasks, eval_names, dataset_name=""):

    if isinstance(eval_names, str):
        eval_names = [eval_names]

    task_id = str(uuid.uuid4())
    eval_tasks[task_id] = {
        "status": "running",
        "eval_names": eval_names,
        "dataset_name": dataset_name,  # 存入任务信息
        "result": None,
        "error": None,
        "report_paths": None
    }
    save_eval_tasks()

    def runner():
        try:
            # 传给评估流水线
            reports, paths = run_evaluate_pipeline(eval_names, dataset_name=dataset_name)

            eval_tasks[task_id]["status"] = "success"
            eval_tasks[task_id]["result"] = reports
            eval_tasks[task_id]["report_paths"] = paths

        except Exception as e:
            eval_tasks[task_id]["status"] = "failed"
            eval_tasks[task_id]["error"] = str(e)
        save_eval_tasks()

    background_tasks.add_task(runner)
    return task_id


def get_evaluate_task(task_id):
    return eval_tasks.get(task_id)


def get_all_evaluate_tasks():
    return eval_tasks