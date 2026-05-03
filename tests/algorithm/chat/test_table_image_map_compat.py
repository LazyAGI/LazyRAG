from chat.components.generate.aggregate import AggregateComponent
from chat.components.generate.output_parser import CustomOutputParser
from lazyllm.tools.rag import DocNode
from processor.table_image_map import normalize_table_image_map, serialize_table_image_map


def test_aggregate_component_serializes_legacy_table_image_map():
    node = DocNode(
        uid='node-1',
        group='block',
        text='表格正文',
        metadata={
            'index': 1,
            'table_image_map': {'表格正文': '![表格](images/table.png)'},
        },
        global_metadata={'docid': 'doc-1'},
    )

    nodes = AggregateComponent()([node])

    assert len(nodes) == 1
    assert isinstance(nodes[0].metadata['table_image_map'], str)
    assert normalize_table_image_map(nodes[0].metadata['table_image_map']) == [
        {'content': '表格正文', 'image': '![表格](images/table.png)'}
    ]


def test_output_parser_replaces_table_text_for_old_and_new_table_image_map():
    parser = CustomOutputParser()
    old_node = DocNode(
        uid='node-old',
        group='block',
        text='标题\n表格正文\n尾注',
        metadata={'table_image_map': {'表格正文': '![旧图](images/old.png)'}},
        global_metadata={'docid': 'doc-1'},
    )
    new_node = DocNode(
        uid='node-new',
        group='block',
        text='标题\n表格正文\n尾注',
        metadata={
            'table_image_map': serialize_table_image_map(
                [{'content': '表格正文', 'image': '![新图](images/new.png)'}]
            )
        },
        global_metadata={'docid': 'doc-1'},
    )

    assert '![旧图](images/old.png)' in parser._replace_table_to_image(old_node)._content
    assert '![新图](images/new.png)' in parser._replace_table_to_image(new_node)._content
