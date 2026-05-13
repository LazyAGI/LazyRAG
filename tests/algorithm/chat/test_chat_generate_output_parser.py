import asyncio
import re

from chat.components.generate.output_parser import CustomOutputParser
from chat.utils.url import is_valid_path
from lazyllm.tools.rag import DocNode
from processor.table_image_map import serialize_table_image_map


def build_node(
    uid='node-1',
    text='LazyRAG supports citations.',
    metadata=None,
    global_metadata=None,
):
    return DocNode(
        uid=uid,
        group='block',
        text=text,
        metadata=metadata or {},
        global_metadata=global_metadata or {
            'docid': 'doc-1',
            'kb_id': 'kb-1',
            'file_name': 'manual.md',
        },
    )


def test_text_with_reference_defaults_sources_to_empty_list():
    parser = CustomOutputParser()

    assert parser.text_with_reference(text='answer') == {
        'think': None,
        'text': 'answer',
        'sources': [],
    }


def test_create_source_node_maps_metadata_and_fallbacks():
    parser = CustomOutputParser()
    node = build_node(
        uid='node-2',
        text='source text',
        metadata={'lazyllm_store_num': 7, 'page': 3, 'bbox': [1, 2, 3, 4]},
        global_metadata={'docid': 'doc-2', 'kb_id': 'kb-2', 'file_name': 'paper.pdf'},
    )

    source = parser.create_source_node(0, node)

    assert source == {
        'index': 0,
        'segment_number': 7,
        'document_id': 'doc-2',
        'page': 3,
        'bbox': [1, 2, 3, 4],
        'dataset_id': 'kb-2',
        'file_name': 'paper.pdf',
        'segement_id': 'node-2',
        'content': 'source text',
        'group_name': 'block',
    }


def test_forward_rewrites_citations_images_and_collects_sources():
    parser = CustomOutputParser()
    node = build_node(
        text='Source mentions ![chart](chart.png).',
        metadata={
            'store_num': 3,
            'page': 2,
            'images': ['https://example.test/assets/chart.png'],
        },
    )

    result = parser.forward('Answer [[1]] with ![chart](chart.png) and remove [[99]].', aggregate=[node])

    assert result['think'] == ''
    assert result['text'] == 'Answer [1](#source "manual.md") with ![chart](https://example.test/assets/chart.png) and remove .'
    assert result['sources'][0]['index'] == 1
    assert result['sources'][0]['segment_number'] == 3
    assert result['sources'][0]['content'] == 'Source mentions ![chart](https://example.test/assets/chart.png).'
    image_urls = re.findall(r'!\[[^\]]*\]\(([^)]+)\)', result['text'])
    assert image_urls == ['https://example.test/assets/chart.png']
    assert all(is_valid_path(url) for url in image_urls)


def test_forward_deduplicates_references_and_escapes_source_title():
    parser = CustomOutputParser()
    node = build_node(global_metadata={'docid': 'doc-1', 'kb_id': 'kb-1', 'file_name': 'a "quoted" & tagged.md'})

    result = parser.forward('First [[1]], second [[1]].', aggregate={1: node})

    assert result['text'] == 'First [1](#source "a &quot;quoted&quot; &amp; tagged.md"), second [1](#source "a &quot;quoted&quot; &amp; tagged.md").'
    assert len(result['sources']) == 1
    assert result['sources'][0]['index'] == 1


def test_forward_drops_empty_reference_and_unknown_image():
    parser = CustomOutputParser()
    node = build_node(text='')

    result = parser.forward('Drop [[1]] and ![missing](missing.png).', aggregate={1: node})

    assert result == {'think': '', 'text': 'Drop  and .', 'sources': []}


def test_forward_rewrites_image_by_fuzzy_basename_match():
    parser = CustomOutputParser()
    node = build_node(metadata={'images': ['https://example.test/assets/chart-final.png']})

    result = parser.forward('See ![chart](chart-fina.png).', aggregate={1: node})

    assert result['text'] == 'See ![chart](https://example.test/assets/chart-final.png).'


def test_forward_splits_think_and_text_when_llm_type_think_enabled():
    parser = CustomOutputParser(llm_type_think=True)
    node = build_node()

    result = parser.forward('reasoning</think>final [[1]]', aggregate=[node])

    assert result['think'] == 'reasoning'
    assert result['text'] == 'final [1](#source "manual.md")'
    assert len(result['sources']) == 1


def test_forward_debug_includes_recall_nodes():
    parser = CustomOutputParser()
    recall = build_node(uid='recall-1', text='recall text', metadata={'store_num': 9})

    result = parser.forward('plain answer', aggregate=[], recall_result=[recall], debug=True)

    assert result['text'] == 'plain answer'
    assert result['recall'][0]['segement_id'] == 'recall-1'
    assert result['recall'][0]['segment_number'] == 9


def test_replace_table_to_image_accepts_serialized_map():
    parser = CustomOutputParser()
    node = build_node(
        text='Before\nTable body\nAfter',
        metadata={
            'table_image_map': serialize_table_image_map(
                [{'content': 'Table body', 'image': '![table](tables/table.png)'}]
            )
        },
    )

    replaced = parser._replace_table_to_image(node)

    assert replaced._content == 'Before\n![table](tables/table.png)\nAfter'


def test_forward_stream_yields_chunks_and_final_sources():
    async def collect():
        parser = CustomOutputParser()
        node = build_node()

        async def chunks():
            yield 'Answer [['
            yield '1]]'

        return [item async for item in parser.forward(chunks(), aggregate={1: node}, stream=True)]

    items = asyncio.run(collect())

    assert items[0] == {'think': None, 'text': 'Answer ', 'sources': []}
    assert items[1] == {'think': None, 'text': '[1](#source "manual.md")', 'sources': []}
    assert items[-1]['text'] == ''
    assert items[-1]['sources'][0]['index'] == 1


def test_forward_stream_buffers_split_image_tokens():
    async def collect():
        parser = CustomOutputParser()
        node = build_node(metadata={'images': ['https://example.test/assets/chart.png']})

        async def chunks():
            yield 'Look ![cha'
            yield 'rt](chart.png)'

        return [item async for item in parser.forward(chunks(), aggregate={1: node}, stream=True)]

    items = asyncio.run(collect())

    assert items == [
        {'think': None, 'text': 'Look ', 'sources': []},
        {'think': None, 'text': '![chart](https://example.test/assets/chart.png)', 'sources': []},
    ]
