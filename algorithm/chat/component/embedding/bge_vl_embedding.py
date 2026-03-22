from lazyllm.module import OnlineEmbeddingModuleBase
from typing import Union, List


class BGEVLEmbedding(OnlineEmbeddingModuleBase):
    def __init__(self, embed_url: str, embed_model_name: str = 'bge-vl'):
        super().__init__('custom', embed_url, 'null', embed_model_name)

    def _encapsulated_data(self, input: Union[List, str], **kwargs):
        images = kwargs.get('images') or []
        json_data = {'text': input, 'images': images}

        assert 'text' in json_data or 'images' in json_data, 'text or images should in input!'
        return json_data

    def _parse_response(self, response: List[float]):
        # 暂时设计为非批量模式
        embedding = response
        return embedding
