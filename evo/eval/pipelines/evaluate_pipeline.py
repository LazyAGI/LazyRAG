from lazyllm import pipeline, loop
from services.evaluate_service import get_eval_queue, evaluate_answer
from utils.writer import build_eval_report, save_eval_report
from utils.logger import log
from concurrent.futures import ThreadPoolExecutor, as_completed


def create_evaluate_task(eval_queue):
    result_list = []
    total = len(eval_queue)

    with ThreadPoolExecutor(max_workers=10) as executor:
        future_map = {
            executor.submit(
                evaluate_answer,
                item["question"],
                item["ground_truth"],
                # item["rag_answer"],
                item["key_points"],
                item["retrieve_contexts"]
            ): item
            for item in eval_queue
        }

        for future in as_completed(future_map):
            item = future_map[future]
            try:
                evaluate_result = future.result()
            except Exception as e:
                evaluate_result = {"error": str(e)}

            result_list.append({
                **item,
                "evaluate_result": evaluate_result
            })

    return result_list


def run_evaluate_pipeline(eval_names,dataset_name=''):
    """
    支持批量评测：传入 eval_names 列表（可单个、可多个）
    返回：所有评测的 report 和 path 列表
    """
    if isinstance(eval_names, str):
        eval_names = [eval_names]

    all_reports = []
    all_paths = []

    for eval_name in eval_names:
        log.info(f"开始执行评测任务：{eval_name}")

        eval_data = get_eval_queue(eval_name=eval_name,dataset_name=dataset_name)
        eval_queue = eval_data["eval_queue"]

        result = create_evaluate_task(eval_queue)
        report = build_eval_report(result, eval_data)
        path = save_eval_report(eval_name, report)

        log.info(f"评测完成：{eval_name}，结果已保存到：{path}")

        all_reports.append(report)
        all_paths.append(path)

    log.info(f"全部批量评测完成！共执行 {len(all_reports)} 个任务")
    return all_reports, all_paths


def run_evaluate_pipeline_id(eval_name, case_id, dataset_name=''):
    log.info(f"开始执行评测任务：{eval_name}")

    eval_data = get_eval_queue(eval_name=eval_name, case_id=case_id,dataset_name=dataset_name)
    eval_queue = eval_data["eval_queue"]

    result = create_evaluate_task(eval_queue)
    report = build_eval_report(result, eval_data)
    path = save_eval_report(eval_name, report)

    log.info(f"评测完成：{eval_name}，结果已保存到：{path}")

    return report, path
