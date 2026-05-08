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

    assert 'Document[[1]]' in context
    assert 'File name: a.md' in context
    assert 'first body' in context
    assert 'Document[[2]]' in context
    assert 'File name: b.md' in context
    assert 'second body' in context


def test_forward_uses_standard_template_when_nodes_exist():
    formatter = RAGContextFormatter()
    nodes = [_FakeNode('knowledge', {'file_name': 'doc.md'})]

    result = formatter.forward(nodes, query='what?', image_files=['x.png'])

    assert LLM_PROMPT_INSTRUCTIONS.strip() in result
    assert 'Reference documents' in result
    assert 'knowledge' in result
    assert 'User question: what?' in result


def test_forward_uses_multimodal_template_when_only_images():
    formatter = RAGContextFormatter()

    result = formatter.forward([], query='image question', image_files=['x.png'])

    assert MULTIMODAL_PROMPT_INSTRUCTIONS.strip() in result
    assert 'image question' in result
    assert 'Reference documents' not in result


def test_forward_falls_back_to_default_without_nodes_or_images():
    formatter = RAGContextFormatter()

    result = formatter.forward(None, query='fallback question')

    assert 'prior knowledge' in result
    assert 'fallback question' in result


def test_create_context_str_handles_missing_filename_and_keeps_numbering():
    formatter = RAGContextFormatter()
    nodes = [
        _FakeNode('alpha', {}),
        _FakeNode('beta', {'file_name': 'b.md'}),
        _FakeNode('gamma', {}),
    ]

    context = formatter._create_context_str(nodes)

    assert context.count('Document[[') == 3
    assert 'Document[[1]]' in context
    assert 'Document[[2]]' in context
    assert 'Document[[3]]' in context
    assert 'File name: None' in context
