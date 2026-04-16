from chat.prompts.agentic import (
    EVALUATOR_PROMPT,
    EXTRACTOR_PROMPT,
    GENERATE_PROMPT,
    GENERATE_PROMPT_ZH,
    PLANREFINE_PROMPT,
    PLANNER_PROMPT,
    QUERYREFINER_PROMPT,
    TOOLCALL_PROMPT,
)


def test_agentic_template_prompts_substitute_required_variables():
    rendered = {
        'planner': PLANNER_PROMPT.substitute(
            tool_num='1',
            tool_description='vector_search: query text',
            original_query='What is LazyRAG?',
        ),
        'toolcall': TOOLCALL_PROMPT.substitute(
            tool_description='vector_search accepts a query parameter',
            original_query='What is LazyRAG?',
            current_goal='Find the definition of LazyRAG',
            previous_step_result='none',
        ),
        'extractor': EXTRACTOR_PROMPT.substitute(
            original_query='What is LazyRAG?',
            inference='',
            current_step='Find the definition of LazyRAG',
            new_nodes='NODE[[0]] LazyRAG is a retrieval system.',
        ),
        'evaluator': EVALUATOR_PROMPT.substitute(
            original_query='What is LazyRAG?',
            plans='[]',
        ),
        'planrefine': PLANREFINE_PROMPT.substitute(
            tool_description='vector_search: query text',
            original_query='What is LazyRAG?',
            executed_plan_and_inferences='[]',
        ),
        'queryrefiner': QUERYREFINER_PROMPT.substitute(
            original_query='What is LazyRAG?',
            inference='',
            retrieval_step='Find the definition of LazyRAG',
            chunks='[]',
        ),
    }

    for text in rendered.values():
        assert '$' not in text
        assert 'JSON' in text


def test_generate_prompts_include_grounding_fields():
    rendered = GENERATE_PROMPT.format(
        inference='LazyRAG is described as a retrieval system.',
        chunks='NODE[[0]] LazyRAG is a retrieval system.',
        query='What is LazyRAG?',
    )
    rendered_zh = GENERATE_PROMPT_ZH.format(
        inference='LazyRAG 是检索系统。',
        chunks='NODE[[0]] LazyRAG 是检索系统。',
        query='LazyRAG 是什么？',
    )

    assert 'Auxiliary inference' in rendered
    assert 'Grounding knowledge' in rendered
    assert 'Question' in rendered
    assert '辅助推理' in rendered_zh
    assert '参考知识' in rendered_zh
    assert '问题' in rendered_zh
