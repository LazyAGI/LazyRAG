from chat.prompts.rag_answer import RAG_ANSWER_SYSTEM


def assert_balanced_curly_braces(text):
    depth = 0
    for char in text:
        if char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
        assert depth >= 0
    assert depth == 0


def test_rag_answer_system_contains_safety_and_identity_rules():
    assert isinstance(RAG_ANSWER_SYSTEM, str)
    assert_balanced_curly_braces(RAG_ANSWER_SYSTEM)
    assert '专业问答助手' in RAG_ANSWER_SYSTEM
    assert '拒绝' in RAG_ANSWER_SYSTEM
    assert '专业问答小助手' in RAG_ANSWER_SYSTEM
