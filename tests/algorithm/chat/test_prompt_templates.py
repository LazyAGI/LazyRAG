from string import Formatter, Template

from chat.components.generate import prompt_formatter as formatter_mod
from chat.prompts import agentic as agentic_prompts
from chat.prompts.rag_answer import RAG_ANSWER_SYSTEM
from chat.prompts.rewrite import MULTITURN_QUERY_REWRITE_PROMPT


def test_format_prompt_templates_only_use_expected_variables():
    templates = {
        'standard_rag_input_cn': (
            formatter_mod.standard_rag_input_cn,
            {'instructions', 'context', 'query'},
        ),
        'image_rag_input_cn': (
            formatter_mod.image_rag_input_cn,
            {'instructions', 'query'},
        ),
        'default_rag_input_cn': (
            formatter_mod.default_rag_input_cn,
            {'query'},
        ),
    }

    formatter = Formatter()

    for _, (template, expected_fields) in templates.items():
        fields = {
            field_name
            for _, field_name, _, _ in formatter.parse(template)
            if field_name is not None
        }
        assert fields == expected_fields
        rendered = template.format(**{field: f'<{field}>' for field in expected_fields})
        for field in expected_fields:
            assert f'<{field}>' in rendered


def test_template_prompts_accept_all_required_substitutions():
    templates = {
        'PLANNER_PROMPT': (
            agentic_prompts.PLANNER_PROMPT,
            {'tool_num', 'tool_description', 'original_query'},
        ),
        'TOOLCALL_PROMPT': (
            agentic_prompts.TOOLCALL_PROMPT,
            {'tool_description', 'original_query', 'current_goal', 'previous_step_result'},
        ),
        'EXTRACTOR_PROMPT': (
            agentic_prompts.EXTRACTOR_PROMPT,
            {'original_query', 'inference', 'current_step', 'new_nodes'},
        ),
        'EVALUATOR_PROMPT': (
            agentic_prompts.EVALUATOR_PROMPT,
            {'original_query', 'plans'},
        ),
        'PLANREFINE_PROMPT': (
            agentic_prompts.PLANREFINE_PROMPT,
            {'original_query', 'executed_plan_and_inferences', 'tool_description'},
        ),
    }

    for _, (template, expected_fields) in templates.items():
        assert isinstance(template, Template)
        actual_fields = {
            match.group('named') or match.group('braced')
            for match in template.pattern.finditer(template.template)
            if match.group('named') or match.group('braced')
        }
        assert actual_fields == expected_fields
        rendered = template.substitute(**{field: f'<{field}>' for field in expected_fields})
        for field in expected_fields:
            assert f'<{field}>' in rendered


def test_generate_prompt_uses_expected_format_variables():
    formatter = Formatter()
    fields = {
        field_name
        for _, field_name, _, _ in formatter.parse(agentic_prompts.GENERATE_PROMPT)
        if field_name is not None
    }

    assert fields == {'query', 'chunks', 'inference'}
    rendered = agentic_prompts.GENERATE_PROMPT.format(
        query='<query>',
        chunks='<chunks>',
        inference='<inference>',
    )
    assert '<query>' in rendered
    assert '<chunks>' in rendered
    assert '<inference>' in rendered


def test_non_template_prompts_keep_literal_braces_only():
    for prompt in [RAG_ANSWER_SYSTEM, MULTITURN_QUERY_REWRITE_PROMPT]:
        assert prompt.count('{') == prompt.count('}')
