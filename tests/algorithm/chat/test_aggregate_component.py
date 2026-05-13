from chat.components.generate.aggregate import AggregateComponent, shorten_image_urls
from lazyllm.tools.rag.doc_node import DocNode


def test_shorten_image_urls_rewrites_remote_images_only():
    markdown = (
        '![a](https://example.com/a.png?token=1)\n'
        '![b](/local/path.png)\n'
        '![c](http://cdn.example.com/c.jpg)'
    )

    rewritten, urls = shorten_image_urls(markdown)

    assert '![a](a.png)' in rewritten
    assert '![b](path.png)' in rewritten
    assert '![c](c.jpg)' in rewritten
    assert urls == [
        'https://example.com/a.png?token=1',
        '/local/path.png',
        'http://cdn.example.com/c.jpg',
    ]


def test_aggregate_component_groups_docid_and_merges_content():
    component = AggregateComponent()
    node1 = DocNode(
        text='body-1 ![img](https://example.com/one.png)',
        metadata={'index': 1, 'title': 'Title One'},
        global_metadata={'docid': 'doc-1'},
    )
    node2 = DocNode(
        text='body-2',
        metadata={'index': 2, 'file_name': 'source.md'},
        global_metadata={'docid': 'doc-1'},
    )
    node3 = DocNode(
        text='other-body',
        metadata={'index': 1},
        global_metadata={'docid': 'doc-2'},
    )

    result = component([node2, node3, node1])

    assert len(result) == 2
    first = result[0]
    assert first.global_metadata['docid'] == 'doc-1'
    assert 'Title One' in first.text
    assert 'body-1' in first.text
    assert 'body-2' in first.text
    assert first.metadata['images'] == ['https://example.com/one.png']
    assert '![img](one.png)' in first.text
    second = result[1]
    assert second.global_metadata['docid'] == 'doc-2'
    assert second.text == 'other-body'


def test_aggregate_component_returns_empty_input_unchanged():
    component = AggregateComponent()

    assert component([]) == []
