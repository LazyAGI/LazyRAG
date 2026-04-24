from pipelines.generate_pipeline import run_generate_pipeline
from pipelines.evaluate_pipeline import run_evaluate_pipeline,run_evaluate_pipeline_id
# ===================== 主逻辑 =====================
if __name__ == "__main__":
    # test generate
    kb_id="ds_e030b437e04837ef4dbb952d45e16902"
    eval_name="研究院"
    algo_id="general_algo"
    # test generate
    run_generate_pipeline(kb_id, algo_id, eval_name)
    eval_names=["研究院"]
    # test eval
    #run_evaluate_pipeline(eval_names)
    # test case
    # run_evaluate_pipeline_id(eval_name,'ce3453e7-cf88-4456-a75e-6b0c82aeedb6')

