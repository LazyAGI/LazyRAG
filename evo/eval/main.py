from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional
from config import HOST, PORT

from tasks.generate_task import create_generate_task, get_generate_task, get_all_generate_tasks
from tasks.evaluate_task import create_evaluate_task, get_evaluate_task, get_all_evaluate_tasks

app = FastAPI(title="评测服务", version="1.0")

class GenerateRequest(BaseModel):
    kb_id: str
    eval_name: Optional[str] = None
    algo_id: Optional[str] = "general_algo"

class EvalRunRequest(BaseModel):
    eval_names: List[str]
    dataset_name: Optional[str] = ""

@app.post("/api/generate")
async def api_generate(req: GenerateRequest, background_tasks: BackgroundTasks):
    task_id = create_generate_task(background_tasks, req.kb_id, req.eval_name, req.algo_id)
    return {"task_id": task_id, "status": "running", "eval_name": req.eval_name}


@app.get("/api/generate_task/{task_id}")
async def api_generate_task(task_id: str):
    task = get_generate_task(task_id)
    return task if task else {"code": 404, "msg": "任务不存在"}


@app.get("/api/generate_tasks")
async def api_all_generate_tasks():
    return get_all_generate_tasks()

@app.post("/api/evaluate")
async def api_evaluate(req: EvalRunRequest, background_tasks: BackgroundTasks):
    task_id = create_evaluate_task(background_tasks, req.eval_names, req.dataset_name)

    return {
        "eval_task_id": task_id,
        "status": "running",
        "eval_names": req.eval_names,
        "dataset_name": req.dataset_name
    }


@app.get("/api/evaluate_task/{task_id}")
async def api_evaluate_task(task_id: str):
    task = get_evaluate_task(task_id)
    return task if task else {"code": 404, "msg": "评测任务不存在"}


@app.get("/api/evaluate_tasks")
async def api_all_eval_tasks():
    return get_all_evaluate_tasks()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True)