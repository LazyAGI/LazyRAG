from typing import Dict, List, Union

from lazyllm.module import OnlineEmbeddingModuleBase


class BgeM3Online(OnlineEmbeddingModuleBase):
    """BgeM3Online"""

    def __init__(self, embed_url, embed_model_name, **kwargs):
        super().__init__(
            embed_url=embed_url,
            embed_model_name=embed_model_name,
            model_series="bge",
            **kwargs
        )

    def _encapsulated_data(self, text: str, **kwargs) -> Dict[str, str]:
        # TODO delete inputs, use 'input' in the future
        json_data = {"inputs": text, "model": self._embed_model_name}
        if len(kwargs) > 0:
            json_data.update(kwargs)

        return json_data

    def _parse_response(self, response: Dict, input: Union[List, str]) -> Union[List[List[float]], List[float]]:
        return response
