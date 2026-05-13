from chat.components.generate.aggregate import AggregateComponent, shorten_image_urls
from lazyllm.tools.rag import DocNode
from processor.table_image_map import serialize_table_image_map


def build_node(uid, docid='doc-1', index=1, text='text', metadata=None):
    return DocNode(
        uid=uid,
        group='block',
        text=text,
        metadata={'index': index, **(metadata or {})},
        global_metadata={'docid': docid, 'kb_id': 'kb-1', 'file_name': 'manual.md'},
    )


def test_shorten_image_urls_rewrites_valid_paths_and_keeps_invalid_links():
    markdown = 'A ![remote](https://example.test/img/chart.png?token=1) and ![bad](img_url).'

    new_markdown, urls = shorten_image_urls(markdown)

    assert isinstance(new_markdown, str)
    assert isinstance(urls, list)
    assert new_markdown == 'A ![remote](chart.png) and ![bad](img_url).'
    assert urls == ['https://example.test/img/chart.png?token=1']


def test_aggregate_component_groups_by_document_and_collects_images():
    first = build_node(
        'n1',
        index=2,
        text='Second ![chart](https://example.test/chart.png)',
        metadata={'title': 'Section 2'},
    )
    second = build_node(
        'n2',
        index=1,
        text='First',
        metadata={
            'table_image_map': serialize_table_image_map(
                [{'content': 'Table body', 'image': '![table](https://example.test/table.png)'}]
            )
        },
    )
    other_doc = build_node('n3', docid='doc-2', index=1, text='Other')

    result = AggregateComponent()([first, other_doc, second])

    assert isinstance(result, list)
    assert len(result) == 2
    doc1 = next(node for node in result if node.global_metadata['docid'] == 'doc-1')
    assert doc1.text == 'First\n\n---\n\nSection 2\nSecond ![chart](chart.png)'
    assert doc1.metadata['images'] == ['https://example.test/chart.png']
    assert 'table_image_map' in doc1.metadata


def test_aggregate_component_returns_empty_input_unchanged():
    assert AggregateComponent()([]) == []
