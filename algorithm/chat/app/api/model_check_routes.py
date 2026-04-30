from typing import Annotated, Optional

from fastapi import APIRouter, Body
import lazyllm

router = APIRouter()


@router.post('/api/model/check', summary='检测模型供应商连通性')
async def check_model_connection(
    model: Annotated[Optional[str], Body(description='模型名称')] = None,
    source: Annotated[Optional[str], Body(description='供应商名称')] = None,
    url: Annotated[Optional[str], Body(description='供应商地址')] = None,
    api_key: Annotated[Optional[str], Body(description='供应商密钥')] = None,
):
    try:
        module = lazyllm.OnlineModule(
            model=model,
            source=source,
            url=url,
            api_key=api_key,
        )
        result = module('hi')
        return {
            'success': True,
            'message': 'model connection is available',
            'model': model,
            'source': source,
            'url': url,
            'result': result,
        }
    except Exception as exc:
        return {
            'success': False,
            'message': str(exc),
            'model': model,
            'source': source,
            'url': url,
        }
