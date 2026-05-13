import asyncio
from types import SimpleNamespace

from chat.components.generate.output_parser import CustomOutputParser


def _make_node(
    *,
    text,
    metadata=None,
    global_metadata=None,
    uid='uid-1',
    group='group-a',
):
    metadata = metadata or {}
    global_metadata = global_metadata or {}
    return SimpleNamespace(
        text=text,
        _content=text,
        metadata=metadata,
        global_metadata=global_metadata,
        _uid=uid,
        _group=group,
    )


def test_output_parser_non_stream_extracts_think_citations_and_image_urls():
    parser = CustomOutputParser(llm_type_think=True)
    node = _make_node(
        text='Source body ![chart](chart.png)',
        metadata={'images': ['https://cdn.example.com/assets/chart.png'], 'page': 2},
        global_metadata={'file_name': 'Doc.md', 'docid': 'doc-1', 'kb_id': 'kb-1'},
    )

    result = parser.forward(
        '<think>plan</think>结论 [[1]] ![chart](chart.png)',
        aggregate=[node],
        debug=True,
        recall_result=[node],
    )

    assert result['think'] == '<think>plan'
    assert '[1](#source "Doc.md")' in result['text']
    assert '![chart](https://cdn.example.com/assets/chart.png)' in result['text']
    assert result['sources'][0]['content'] == 'Source body ![chart](https://cdn.example.com/assets/chart.png)'
    assert result['recall'][0]['document_id'] == 'doc-1'
    assert isinstance(result['sources'], list)
    assert isinstance(result['recall'], list)


def test_output_parser_stream_yields_chunks_and_final_sources():
    parser = CustomOutputParser(llm_type_think=True)
    node = _make_node(
        text='Source body',
        metadata={'page': 5},
        global_metadata={'file_name': 'Doc.md', 'docid': 'doc-1', 'kb_id': 'kb-1'},
    )

    async def _astream():
        for chunk in ['<thi', 'nk>plan</think>事实 [[1]]']:
            yield chunk

    async def _collect():
        chunks = []
        async for item in parser.forward(_astream(), aggregate=[node], stream=True):
            chunks.append(item)
        return chunks

    chunks = asyncio.run(_collect())

    assert chunks == [
        {'think': '<think>plan', 'text': None, 'sources': []},
        {'think': None, 'text': '事实 ', 'sources': []},
        {'think': None, 'text': '[1](#source "Doc.md")', 'sources': []},
        {
            'think': None,
            'text': '',
            'sources': [{
                'index': 1,
                'segment_number': -1,
                'document_id': 'doc-1',
                'page': 5,
                'bbox': [],
                'dataset_id': 'kb-1',
                'file_name': 'Doc.md',
                'segement_id': 'uid-1',
                'content': 'Source body',
                'group_name': 'group-a',
            }],
        },
    ]
