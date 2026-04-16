from chat.prompts.rewrite import MULTITURN_QUERY_REWRITE_PROMPT


def test_multiturn_rewrite_prompt_defines_strict_json_schema():
    assert '仅输出一个 JSON 对象' in MULTITURN_QUERY_REWRITE_PROMPT
    assert '"rewritten_query"' in MULTITURN_QUERY_REWRITE_PROMPT
    assert '"constraints"' in MULTITURN_QUERY_REWRITE_PROMPT
    assert 'current_date' in MULTITURN_QUERY_REWRITE_PROMPT
