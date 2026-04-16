from chat.prompts.rag_answer import RAG_ANSWER_SYSTEM


def test_rag_answer_system_contains_safety_and_identity_rules():
    assert '专业问答助手' in RAG_ANSWER_SYSTEM
    assert '拒绝' in RAG_ANSWER_SYSTEM
    assert '专业问答小助手' in RAG_ANSWER_SYSTEM
