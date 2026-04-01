from typing import Dict, List, Union

from lazyllm.module.llms.onlinemodule.base import LazyLLMOnlineEmbedModuleBase


class BgeM3Embed(LazyLLMOnlineEmbedModuleBase):
    NO_PROXY = True

    def __init__(self, embed_url: str = '', embed_model_name: str = 'custom', api_key: str = None,
                 skip_auth: bool = True, batch_size: int = 16, **kw):
        super().__init__(model_series='bge', embed_url=embed_url, api_key='' if skip_auth else (api_key or ''),
                         embed_model_name=embed_model_name,
                         skip_auth=skip_auth, batch_size=batch_size, **kw)

    def _set_embed_url(self):
        pass

    def _encapsulated_data(self, input: Union[List, str], **kwargs):
        model = kwargs.get('model', self._embed_model_name)
        extras = {k: v for k, v in kwargs.items() if k not in ('model',)}
        if isinstance(input, str):
            json_data: Dict = {'inputs': input}
            if model:
                json_data['model'] = model
            json_data.update(extras)
            return json_data
        text_batch = [input[i: i + self._batch_size] for i in range(0, len(input), self._batch_size)]
        out = []
        for texts in text_batch:
            item: Dict = {'inputs': texts}
            if model:
                item['model'] = model
            item.update(extras)
            out.append(item)
        return out

    def _parse_response(self, response: Union[Dict, List], input: Union[List, str]
                        ) -> Union[List[float], List[List[float]], Dict]:
        if isinstance(response, dict):
            if 'data' in response:
                return super()._parse_response(response, input)
            return response
        if isinstance(response, list):
            if not response:
                raise RuntimeError('empty embedding response')
            if isinstance(input, str):
                first = response[0]
                return response if isinstance(first, float) else first
            return response
        raise RuntimeError(f'unexpected embedding response type: {type(response)!r}')
