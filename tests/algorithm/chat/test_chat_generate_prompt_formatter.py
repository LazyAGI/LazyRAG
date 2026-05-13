from string import Formatter

from chat.components.generate.prompt_formatter import (
    LLM_PROMPT_INSTRUCTIONS,
    MULTIMODAL_PROMPT_INSTRUCTIONS,
    RAGContextFormatter,
    default_rag_input_en,
    image_rag_input_en,
    standard_rag_input_en,
)


class DummyNode:
    def __init__(self, text='node text', metadata=None):
        self.text = text
        self.metadata = metadata or {}


def assert_valid_format_prompt(prompt, expected_fields):
    fields = [field_name for _, field_name, _, _ in Formatter().parse(prompt) if field_name]
    assert fields == expected_fields
    assert isinstance(prompt.format(**{field: field for field in expected_fields}), str)


def test_prompt_formatter_templates_have_valid_variable_braces():
    assert isinstance(LLM_PROMPT_INSTRUCTIONS, str)
    assert isinstance(MULTIMODAL_PROMPT_INSTRUCTIONS, str)
    assert_valid_format_prompt(standard_rag_input_en, ['instructions', 'context', 'query'])
    assert_valid_format_prompt(image_rag_input_en, ['instructions', 'query'])
    assert_valid_format_prompt(default_rag_input_en, ['query'])


def test_rag_context_formatter_uses_context_branch_and_output_type():
    formatter = RAGContextFormatter()
    nodes = [DummyNode(text='LazyRAG content', metadata={'file_name': 'manual.md'})]

    result = formatter.forward(nodes, query='What is LazyRAG?')

    assert isinstance(result, str)
    assert 'Reference' in result or 'reference' in result or 'document' in result.lower() or 'Document' in result
    assert '[[1]]' in result
    assert 'manual.md' in result
    assert 'What is LazyRAG?' in result


def test_rag_context_formatter_uses_image_only_and_default_branches():
    formatter = RAGContextFormatter()

    image_result = formatter.forward([], image_files=['/tmp/chart.png'], query='Describe the image')
    default_result = formatter.forward([], query='General question')

    assert isinstance(image_result, str)
    assert 'Describe the image' in image_result
    assert isinstance(default_result, str)
    assert 'General question' in default_result
