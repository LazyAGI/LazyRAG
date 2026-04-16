from lazyllm.tools.rag import DocNode
from processor.table_image_map import normalize_table_image_map, serialize_table_image_map

from parsing.transform.post_func import (
    GroupFilterNodeParser,
    LayoutNodeParser,
    MergeNodeParser,
    NodeTextClear,
    ParagraphType,
)


def test_node_text_clear_normalizes_full_width_text_and_drops_empty_nodes():
    nodes = [
        DocNode(text='ＡＢＣ１２３', metadata={'file_name': 'a.pdf'}),
        DocNode(text='', metadata={'file_name': 'a.pdf'}),
    ]

    result = NodeTextClear().forward(nodes)

    assert [node.text for node in result] == ['ABC123']
    assert result[0].metadata['file_name'] == 'a.pdf'


def test_layout_node_parser_marks_time_index_and_plain_text():
    nodes = [
        DocNode(text='普通正文', metadata={'file_name': 'b.pdf'}),
        DocNode(text='2024年1月2日', metadata={'file_name': 'a.pdf'}),
        DocNode(text='1.1 标题内容', metadata={'file_name': 'a.pdf'}),
    ]

    result = LayoutNodeParser().forward(nodes)

    assert [node.metadata['file_name'] for node in result] == ['a.pdf', 'a.pdf', 'b.pdf']
    assert [node.metadata['index'] for node in result] == [0, 1, 0]
    assert result[0].metadata['text_type'] == ParagraphType.Time_text
    assert result[1].metadata['text_type'] == ParagraphType.Index_text
    assert result[2].metadata['text_type'] == ParagraphType.Text


def test_merge_node_parser_merges_text_bbox_lines_and_table_image_map():
    table_map = serialize_table_image_map([{'content': 'table markdown', 'image': '![表](images/table.png)'}])
    group = [
        DocNode(
            text='first',
            metadata={'file_name': 'a.pdf', 'page': 1, 'bbox': [10, 20, 30, 40], 'type': 'text'},
        ),
        DocNode(
            text='table markdown',
            metadata={
                'file_name': 'a.pdf',
                'page': 1,
                'bbox': [5, 25, 35, 45],
                'type': 'table',
                'table_image_map': table_map,
            },
        ),
        DocNode(
            text='second page',
            metadata={'file_name': 'a.pdf', 'page': 2, 'bbox': [1, 2, 3, 4], 'type': 'text'},
        ),
    ]

    result = MergeNodeParser().forward([group])

    assert len(result) == 1
    assert result[0].text == 'first\ntable markdown\nsecond page'
    assert result[0].metadata['bbox'] == [5, 20, 35, 45]
    assert result[0].metadata['lines'] == [
        {'content': 'first', 'bbox': [10, 20, 30, 40], 'type': 'text', 'page': 1},
        {'content': 'table markdown', 'bbox': [5, 25, 35, 45], 'type': 'table', 'page': 1},
        {'content': 'second page', 'bbox': [1, 2, 3, 4], 'type': 'text', 'page': 2},
    ]
    assert normalize_table_image_map(result[0].metadata['table_image_map']) == [
        {'content': 'table markdown', 'image': '![表](images/table.png)'}
    ]


def test_group_filter_node_parser_removes_table_of_contents_group():
    toc_group = [DocNode(text='目 录', metadata={'type': 'text'})]
    body_group = [DocNode(text='正文', metadata={'type': 'text'})]

    assert GroupFilterNodeParser().forward([toc_group, body_group]) == [body_group]
