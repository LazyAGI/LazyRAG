from typing import Dict, List, Union

from lazyllm.module import OnlineEmbeddingModuleBase


QWEN3_DEFAULT_TASK_DESCRIPTION = 'Given a web search query, retrieve relevant passages that answer the query'


class Qwen3EmbeddingModule(OnlineEmbeddingModuleBase):
    """Qwen3EmbeddingModule"""

    def __init__(
            self,
            embed_url,
            embed_model_name,
            api_key,
            model_series):
        super().__init__(
            embed_url=embed_url, embed_model_name=embed_model_name, api_key=api_key, model_series=model_series
        )
    
    def _get_detailed_instruct(self, task_description: str, query: str) -> str:
        return f'Instruct: {task_description}\nQuery:{query}'

    def _encapsulated_data(self, text: str, **kwargs) -> Dict[str, str]:
        instruct = kwargs.pop('instruct', None)
        text = self._get_detailed_instruct(instruct, text) if instruct else text
        json_data = {"input": text, "model": self._embed_model_name}
        if len(kwargs) > 0:
            json_data.update(kwargs)
        return json_data

    def _parse_response(self, response: Union[List[List[str]], Dict]) -> Union[List[List[str]], Dict]:
        res = response['data'][0]['embedding']
        return res


if __name__ == "__main__":
    embed_url = "http://10.119.27.151:2270/v1/embeddings"
    embed_model_name = "Qwen3-Embedding-8B"
    api_key = "null"
    model_series = "qwen"
    embedder = Qwen3EmbeddingModule(embed_url, embed_model_name, api_key, model_series)
    result = embedder("你好")
    print(result)
