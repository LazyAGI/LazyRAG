import json

from evo.task_planner_agent import TaskPlannerAgent, build_task_plans, generate_task_plan_output


def _write_project_file(tmp_path, relative_path):
    path = tmp_path / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('# test target\n', encoding='utf-8')
    return path


def _sample_report():
    return {
        'report_id': 'report-test-001',
        'summary': {'top_issue': '检索召回不足导致生成缺少证据'},
        'action_list': {
            'action_1': {
                'priority': 1,
                'owner_team_suggestion': 'retrieval',
                'trigger_metric': 'context_recall',
                'trigger_cases': ['case-001'],
                'validation_cases': ['case-001'],
                'evidence_confidence': 0.85,
                'hypothesis': '提升 topk 可以恢复关键法规 chunk 的召回',
                'symptoms': 'context_recall=0 且 doc_recall=0',
                'evidence_finding': 'case-001 关键短语未出现在 retrieved chunks 中',
                'verification_metric': 'context_recall',
                'rollback_metric': 'answer_correctness',
                'changes': {
                    'retriever': {
                        'type': 'config',
                        'goal': '提高法规类查询的相关文档召回率',
                        'suggested_changes': [{
                            'file': 'algorithm/chat/pipelines/builders/get_retriever.py',
                            'param': 'topk',
                            'line': 12,
                            'current_raw': 'topk=20',
                            'suggested_action': 'increase topk for recall-sensitive queries',
                            'risk_level': 'medium',
                        }],
                    }
                },
            },
            'action_2': {
                'priority': 2,
                'owner_team_suggestion': 'generation',
                'trigger_metric': 'faithfulness',
                'trigger_cases': ['case-002'],
                'validation_cases': ['case-002'],
                'evidence_confidence': 0.65,
                'hypothesis': '无相关上下文时生成器应返回信息不足',
                'symptoms': 'faithfulness 下降并出现 hallucination',
                'evidence_finding': '答案编造了报告中不存在的机构名称',
                'verification_metric': 'faithfulness',
                'changes': {
                    'generator': {
                        'type': 'guardrail',
                        'suggested_changes': [{
                            'file': 'algorithm/chat/prompts/rag_answer.py',
                            'param': 'insufficient_context_fallback',
                            'suggested_action': 'add fallback instruction',
                        }],
                    }
                },
            },
        },
        'key_findings': {
            'finding_1': {
                'field': 'retrieval',
                'severity': 'high',
                'behavior': '检索阶段未召回任何 Ground Truth chunk',
            },
            'finding_2': {
                'field': 'generation',
                'severity': 'medium',
                'behavior': '生成阶段在缺少证据时输出确定性答案',
            },
        },
        'causal_chains': {
            'case-001': {
                'dataset_id': 'dataset-001',
                'bottleneck_stage': 'retrieval',
                'bottleneck_impact': 0.9,
                'chain': [{
                    'stage': 'retrieval',
                    'input_summary': 'Query: 法规适用范围是什么',
                    'output_summary': 'retrieved chunks empty',
                    'information_lost': '关键法规条款在检索阶段丢失',
                    'impact_score': 0.9,
                    'details': {'chunks_retrieved': 0, 'missing_keys': ['法规条款']},
                }],
            }
        },
        'interaction_effects': [{
            'stages': ['retrieval', 'generation'],
            'cascade_type': 'retrieval_to_generation',
            'description': '检索零召回放大了生成幻觉',
            'suggested_fix': '先恢复检索召回，再收紧生成兜底',
        }],
    }


def test_build_task_plans_groups_actions_and_enriches_context(monkeypatch, tmp_path):
    _write_project_file(tmp_path, 'algorithm/chat/pipelines/builders/get_retriever.py')
    _write_project_file(tmp_path, 'algorithm/chat/prompts/rag_answer.py')
    monkeypatch.chdir(tmp_path)

    tasks = build_task_plans(_sample_report(), tmp_path)

    assert [task['module'] for task in tasks] == ['retriever', 'generator']

    retriever_task = tasks[0]
    assert retriever_task['task_id'] == 'T001'
    assert retriever_task['report_id'] == 'report-test-001'
    assert retriever_task['change_type'] == 'config'
    assert retriever_task['goal'] == '提高法规类查询的相关文档召回率'
    assert retriever_task['risk'] == 3
    assert retriever_task['priority'] == 1
    assert retriever_task['trigger_cases'] == ['case-001']
    assert retriever_task['trigger_metric'] == 'context_recall'
    assert retriever_task['confidence'] == 0.85
    assert retriever_task['cascade_type'] == 'retrieval_to_generation'
    assert retriever_task['bottleneck_stage'] == 'retrieval'
    assert retriever_task['change_targets'][0]['file'] == (
        'algorithm/chat/pipelines/builders/get_retriever.py'
    )
    assert any('context_recall' in step for step in retriever_task['plan'])
    assert any('关键法规条款' in item for item in retriever_task['evidence'])

    generator_task = tasks[1]
    assert generator_task['task_id'] == 'T002'
    assert generator_task['depends_on'] == ['T001']
    assert generator_task['change_type'] == 'guardrail'
    assert generator_task['risk'] == 2
    assert generator_task['trigger_cases'] == ['case-002']


def test_task_planner_agent_forward_formats_validation_feedback_task(tmp_path):
    agent = TaskPlannerAgent(code_root=tmp_path)
    validation_result = {
        'unit_test': False,
        'pipeline_test': False,
        'case_validation': {'case-001': False},
        'details': [{
            'type': 'unit',
            'name': 'test_context_recall',
            'command': 'pytest tests/algorithm/test_retriever.py',
            'return_code': 1,
            'stderr': 'AssertionError: context_recall did not improve',
            'passed': False,
        }],
        'next_round_hints': ['检查 get_retriever.py 中 topk 配置是否生效'],
    }

    output = agent.forward(
        report=_sample_report(),
        validation_result=validation_result,
        output_format='task_plans',
    )

    assert output['report_id'] == 'report-test-001'
    assert output['status'] == 'repair_planned'
    assert 'case' not in output
    assert len(output['task_plans']) == 1

    task = output['task_plans'][0]
    assert task['module'] == 'test_validation'
    assert task['change_type'] == 'fix'
    assert task['trigger_metric'] == 'test_validation_gate'
    assert task['risk'] == 2
    assert any('unit_test' in item for item in task['evidence'])
    assert any('test_context_recall' in step for step in task['plan'])
    assert task['report_context']['related_modules'] == ['retriever']
    assert task['report_context']['trigger_cases'] == ['case-001']


def test_generate_task_plan_output_writes_json_file(monkeypatch, tmp_path):
    _write_project_file(tmp_path, 'algorithm/chat/pipelines/builders/get_retriever.py')
    monkeypatch.chdir(tmp_path)
    report_path = tmp_path / 'report.json'
    report_path.write_text(json.dumps(_sample_report(), ensure_ascii=False), encoding='utf-8')
    output_path = tmp_path / 'plan.json'

    result = generate_task_plan_output(
        report_path,
        code_root=tmp_path,
        output=output_path,
        output_format='json',
        schema='simple',
    )

    assert output_path.exists()
    saved = json.loads(output_path.read_text(encoding='utf-8'))
    assert saved == json.loads(result)
    assert saved['status'] == 'planned'
    assert list(saved['task_plans'][0]) == [
        'task_id',
        'report_id',
        'module',
        'change_type',
        'goal',
        'plan',
        'risk',
        'priority',
    ]
