import pytest

from chat.components.tmp.local_models import BgeM3Embed


def test_bgem3_encapsulated_data_handles_single_string():
    embed = BgeM3Embed(embed_url='http://example.com/embed', batch_size=2)

    payload = embed._encapsulated_data('hello', model='m1', normalize=True)

    assert payload == {'inputs': 'hello', 'model': 'm1', 'normalize': True}


def test_bgem3_encapsulated_data_batches_list_input():
    embed = BgeM3Embed(embed_url='http://example.com/embed', batch_size=2)

    payload = embed._encapsulated_data(['a', 'b', 'c'], model='m2', normalize=False)

    assert payload == [
        {'inputs': ['a', 'b'], 'model': 'm2', 'normalize': False},
        {'inputs': ['c'], 'model': 'm2', 'normalize': False},
    ]


def test_bgem3_parse_response_supports_local_service_shapes():
    embed = BgeM3Embed(embed_url='http://example.com/embed')

    assert embed._parse_response({'custom': 1}, 'hello') == {'custom': 1}
    assert embed._parse_response([0.1, 0.2], 'hello') == [0.1, 0.2]
    assert embed._parse_response([[0.1, 0.2], [0.3, 0.4]], ['a', 'b']) == [
        [0.1, 0.2],
        [0.3, 0.4],
    ]


def test_bgem3_parse_response_rejects_invalid_payload():
    embed = BgeM3Embed(embed_url='http://example.com/embed')

    with pytest.raises(RuntimeError, match='empty embedding response'):
        embed._parse_response([], 'hello')
    with pytest.raises(RuntimeError, match='unexpected embedding response type'):
        embed._parse_response('bad', 'hello')
