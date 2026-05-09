from chat.prompts.rewrite import MULTITURN_QUERY_REWRITE_PROMPT


def assert_balanced_curly_braces(text):
    depth = 0
    for char in text:
        if char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
        assert depth >= 0
    assert depth == 0


def test_multiturn_rewrite_prompt_defines_strict_json_schema():
    assert isinstance(MULTITURN_QUERY_REWRITE_PROMPT, str)
    assert_balanced_curly_braces(MULTITURN_QUERY_REWRITE_PROMPT)
    assert 'Output only one JSON object' in MULTITURN_QUERY_REWRITE_PROMPT
    assert '"rewritten_query"' in MULTITURN_QUERY_REWRITE_PROMPT
    assert '"constraints"' in MULTITURN_QUERY_REWRITE_PROMPT
    assert 'current_date' in MULTITURN_QUERY_REWRITE_PROMPT
