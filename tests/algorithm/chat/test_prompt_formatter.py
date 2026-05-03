from chat.components.generate.prompt_formatter import (
    LLM_PROMPT_INSTRUCTIONS,
    MULTIMODAL_PROMPT_INSTRUCTIONS,
    RAGContextFormatter,
)


class _FakeNode:
    def __init__(self, text, metadata):
        self.text = text
        self.metadata = metadata


def test_create_context_str_includes_order_and_filename():
    formatter = RAGContextFormatter()
    nodes = [
        _FakeNode('first body', {'file_name': 'a.md'}),
        _FakeNode('second body', {'file_name': 'b.md'}),
    ]

    context = formatter._create_context_str(nodes)

    assert '文档[[1]]' in context
    assert '文档名：a.md' in context
    assert 'first body' in context
    assert '文档[[2]]' in context
    assert '文档名：b.md' in context
    assert 'second body' in context


def test_forward_uses_standard_template_when_nodes_exist():
    formatter = RAGContextFormatter()
    nodes = [_FakeNode('knowledge', {'file_name': 'doc.md'})]

    result = formatter.forward(nodes, query='what?', image_files=['x.png'])

    assert LLM_PROMPT_INSTRUCTIONS.strip() in result
    assert '参考文档' in result
    assert 'knowledge' in result
    assert '用户问题：what?' in result


def test_forward_uses_multimodal_template_when_only_images():
    formatter = RAGContextFormatter()

    result = formatter.forward([], query='image question', image_files=['x.png'])

    assert MULTIMODAL_PROMPT_INSTRUCTIONS.strip() in result
    assert '用户问题：image question' in result
    assert '参考文档' not in result


def test_forward_falls_back_to_default_without_nodes_or_images():
    formatter = RAGContextFormatter()

    result = formatter.forward(None, query='fallback question')

    assert '使用你的先验知识回答用户的问题' in result
    assert '用户问题：fallback question' in result


def test_create_context_str_handles_missing_filename_and_keeps_numbering():
    formatter = RAGContextFormatter()
    nodes = [
        _FakeNode('alpha', {}),
        _FakeNode('beta', {'file_name': 'b.md'}),
        _FakeNode('gamma', {}),
    ]

    context = formatter._create_context_str(nodes)

    assert context.count('文档[[') == 3
    assert '文档[[1]]' in context
    assert '文档[[2]]' in context
    assert '文档[[3]]' in context
    assert '文档名：None' in context
