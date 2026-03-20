import json
from lazyllm.module import OnlineEmbeddingModuleBase

# class BGEM3SparseEmbedding(OnlineEmbeddingModuleBase):
#     def __init__(self, embed_url: str, embed_model_name: str = 'bge-m3'):
#         super().__init__("custom", embed_url, "sk123", embed_model_name)

#     def _encapsulated_data(self, text:str, **kwargs):
#         json_data = {
#             "input": text,
#             "model": self._embed_model_name
#         }
#         return json_data

#     def _parse_response(self, response: dict[str, any]):
#         embedding_dic_string = response['data'][0]['embedding']
#         embedding_dic_string = embedding_dic_string.replace("'", '"')
#         embedding_dic = json.loads(embedding_dic_string)
#         return embedding_dic['sparse']


# class BGEM3DenseEmbedding(OnlineEmbeddingModuleBase):
#     def __init__(self, embed_url: str, embed_model_name: str = 'bge-m3'):
#         super().__init__("custom", embed_url, "sk123", embed_model_name)

#     def _encapsulated_data(self, text:str, **kwargs):
#         json_data = {
#             "input": text,
#             "model": self._embed_model_name
#         }
#         return json_data

#     def _parse_response(self, response: dict[str, any]):
#         embedding_dic_string = response['data'][0]['embedding']
#         embedding_dic_string = embedding_dic_string.replace("'", '"')
#         embedding_dic = json.loads(embedding_dic_string)
#         return embedding_dic['dense']


# class BGEM3Reranking(OnlineEmbeddingModuleBase):
#     def __init__(self, embed_url: str, embed_model_name: str = 'bge-reranker-large'):
#         super().__init__("custom", embed_url, "sk123", embed_model_name)

#     @property
#     def type(self):
#         return "ONLINE_RERANK"

#     def _encapsulated_data(self, text: str, documents: list, **kwargs):
#         # 将数据包装为您的服务需要的数据格式
#         json_data = {
#             "model": self._embed_model_name,
#             "query": text,
#             "documents": documents
#         }
#         return json_data

#     def _parse_response(self, response: dict[str, any]):
#         # 解析您的服务返回的数据，返回 embedding 部分即可
#         results = response['results']
#         return [(result["index"], result["relevance_score"]) for result in results]


# from lazyllm.module.llms.onlinemodule import LazyLLMOnlineEmbedModuleBase
class BgeReasonerOnline(OnlineEmbeddingModuleBase):
    def __init__(self, embed_url: str, embed_model_name: str = 'bge-m3', api_key: str = ''):
        super().__init__(model_series='bge', embed_url=embed_url, embed_model_name=embed_model_name, api_key=api_key)

    def _encapsulated_data(self, text:str, **kwargs):
        json_data = {
            "input": text,
            "model": self._embed_model_name
        }
        return json_data

    def _parse_response(self, response: dict[str, any], input):
        import lazyllm
        lazyllm.LOG.info("here")
        lazyllm.LOG.info(response)
        embedding_dic_string = response['data'][0]['embedding']
        # embedding_dic_string = embedding_dic_string.replace("'", '"')
        # embedding_dic = json.loads(embedding_dic_string)
        return embedding_dic_string

if __name__ == "__main__":
    embed_url = "http://10.119.28.105:2280/v1/embeddings"
    embed_model_name = "BGE-reasoner"
    # import lazyllm
    # model = lazyllm.TrainableModule(url=embed_url, model=embed_model_name)
    # exit()
    # model = lazyllm.TrainableModule('bge-m3')
    from lazyllm import OnlineEmbeddingModule

    embedding = BgeReasonerOnline(embed_url, embed_model_name)
    emb = embedding("Hello, world!")

    print(emb)
    print(len(emb))
