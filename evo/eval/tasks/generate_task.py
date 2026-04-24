import uuid
import json
import os
from pipelines.generate_pipeline import run_generate_pipeline
from fastapi import BackgroundTasks
from utils.writer import write_full_eval_set, build_full_eval_set
from datetime import datetime
from config import DATA_PATH

TASK_FILE = DATA_PATH + "/tasks/generate_tasks.json"

# 启动时加载历史任务
if os.path.exists(TASK_FILE):
    with open(TASK_FILE, "r", encoding="utf-8") as f:
        tasks = json.load(f)
else:
    tasks = {}


# 保存任务到文件
def save_tasks():
    with open(TASK_FILE, "w", encoding="utf-8") as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)


def create_generate_task(
        background_tasks: BackgroundTasks,
        kb_id: str,
        eval_name: str = None,
        algo_id: str = "general_algo"
):
    task_id = str(uuid.uuid4())

    if not eval_name:
        eval_name = f"eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    tasks[task_id] = {
        "status": "running",
        "kb_id": kb_id,
        "algo_id": algo_id,
        "eval_name": eval_name,
        "result": None,
        "file_path": None
    }
    save_tasks()

    def runner():
        try:
            file_path, final_data = run_generate_pipeline(kb_id, algo_id, eval_name)

            tasks[task_id]["result"] = final_data
            tasks[task_id]["file_path"] = file_path
            tasks[task_id]["status"] = "success"

        except Exception as e:
            tasks[task_id]["status"] = "failed"
            tasks[task_id]["error"] = str(e)
        save_tasks()  # 保存

    background_tasks.add_task(runner)
    return task_id


def get_generate_task(task_id: str):
    return tasks.get(task_id)


def get_all_generate_tasks():
    return tasks
