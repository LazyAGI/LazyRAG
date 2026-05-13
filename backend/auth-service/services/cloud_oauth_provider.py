from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass
class CloudTokenPayload:
    access_token: str
    expires_at: datetime | None = None
    refresh_token: str | None = None
    token_type: str = 'Bearer'


class CloudOAuthProvider(Protocol):
    def provider_name(self) -> str:
        ...

    def build_authorize_url(
        self,
        *,
        client_id: str,
        redirect_uri: str,
        scope: str,
        state: str,
    ) -> str:
        ...

    def exchange_code(
        self,
        *,
        client_id: str,
        client_secret: str,
        code: str,
        redirect_uri: str,
    ) -> CloudTokenPayload:
        ...

    def refresh_access_token(
        self,
        *,
        client_id: str,
        client_secret: str,
        refresh_token: str,
    ) -> CloudTokenPayload:
        ...

    def acquire_tenant_access_token(
        self,
        *,
        client_id: str,
        client_secret: str,
    ) -> CloudTokenPayload:
        ...
