from fastapi import APIRouter, Depends

from core.deps import require_internal_service_token
from schemas.cloud_oauth import (
    CloudConnectionCreateBody,
    CloudConnectionCreateResponse,
    CloudConnectionResponse,
    CloudConnectionTokenResponse,
    CloudOAuthAuthorizeURLBody,
    CloudOAuthAuthorizeURLResponse,
    CloudOAuthCallbackBody,
    CloudOAuthCallbackResponse,
)
from services.cloud_oauth_service import cloud_oauth_service


router = APIRouter(prefix='/v1/cloud', tags=['cloud-oauth'])


@router.post('/{provider}/connections', response_model=CloudConnectionCreateResponse)
def create_connection(provider: str, body: CloudConnectionCreateBody):
    return cloud_oauth_service.create_connection(
        provider=provider,
        tenant_id=body.tenant_id,
        auth_mode=body.auth_mode,
        client_id=body.client_id,
        client_secret=body.client_secret,
        provider_options=body.provider_options,
    )


@router.post('/{provider}/oauth/authorize-url', response_model=CloudOAuthAuthorizeURLResponse)
def oauth_authorize_url(provider: str, body: CloudOAuthAuthorizeURLBody):
    return cloud_oauth_service.create_authorize_url(
        provider=provider,
        tenant_id=body.tenant_id,
        auth_mode=body.auth_mode,
        client_id=body.client_id,
        client_secret=body.client_secret,
        redirect_uri=body.redirect_uri or '',
        scope=body.scope,
        state=body.state,
        provider_options=body.provider_options,
    )


@router.post('/{provider}/oauth/callback', response_model=CloudOAuthCallbackResponse)
def oauth_callback(provider: str, body: CloudOAuthCallbackBody):
    return cloud_oauth_service.oauth_callback(
        provider=provider,
        tenant_id=body.tenant_id,
        connection_id=body.connection_id,
        code=body.code,
        state=body.state,
        redirect_uri=body.redirect_uri,
    )


@router.get('/connections/{connection_id}', response_model=CloudConnectionResponse)
def get_connection(connection_id: str):
    return cloud_oauth_service.get_connection(connection_id)


@router.get('/connections/{connection_id}/token', response_model=CloudConnectionTokenResponse)
def get_connection_token(
    connection_id: str,
    _internal: None = Depends(require_internal_service_token),  # noqa: B008
):
    return cloud_oauth_service.get_access_token(connection_id)
