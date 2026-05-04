import secrets
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from core.cloud_crypto import decrypt_json, encrypt_json
from core.database import SessionLocal
from core.errors import AppException, ErrorCodes, raise_error
from repositories import CloudAuthConnectionRepository
from services.cloud_oauth_provider import CloudOAuthProvider, CloudTokenPayload
from services.providers import FeishuOAuthProvider


_AUTH_MODES = {'tenant', 'oauth_user', 'service_account'}
_TOKEN_REFRESH_BUFFER_SECONDS = 300
_OAUTH_STATE_TTL_MINUTES = 10


@dataclass
class _TokenCacheItem:
    provider: str
    access_token: str
    token_type: str
    expires_at: datetime | None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None) -> str:
    if dt is None:
        return ''
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _parse_dt(raw: Any) -> datetime | None:
    if not raw:
        return None
    if isinstance(raw, datetime):
        dt = raw
    elif isinstance(raw, str):
        try:
            dt = datetime.fromisoformat(raw.replace('Z', '+00:00'))
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _truncate_error(err: Exception) -> str:
    msg = str(err or '').strip()
    if len(msg) > 1000:
        return msg[:1000]
    return msg


class CloudOAuthService:
    def __init__(self):
        feishu = FeishuOAuthProvider()
        self._providers: dict[str, CloudOAuthProvider] = {feishu.provider_name(): feishu}
        self._cache_lock = threading.Lock()
        self._token_cache: dict[str, _TokenCacheItem] = {}

    def _provider(self, provider: str) -> CloudOAuthProvider:
        key = (provider or '').strip().lower()
        p = self._providers.get(key)
        if p is None:
            raise_error(ErrorCodes.CLOUD_PROVIDER_UNSUPPORTED, extra_msg=provider)
        return p

    @staticmethod
    def _validate_auth_mode(auth_mode: str) -> str:
        mode = (auth_mode or 'oauth_user').strip().lower()
        if mode not in _AUTH_MODES:
            raise_error(ErrorCodes.CLOUD_AUTH_MODE_INVALID, extra_msg=auth_mode)
        return mode

    @staticmethod
    def _is_token_valid(access_token: str, expires_at: datetime | None) -> bool:
        if not access_token:
            return False
        if expires_at is None:
            return True
        return expires_at > (_utcnow() + timedelta(seconds=_TOKEN_REFRESH_BUFFER_SECONDS))

    def _cache_get(self, connection_id: str) -> _TokenCacheItem | None:
        key = (connection_id or '').strip()
        if not key:
            return None
        with self._cache_lock:
            item = self._token_cache.get(key)
        if item is None:
            return None
        if self._is_token_valid(item.access_token, item.expires_at):
            return item
        with self._cache_lock:
            self._token_cache.pop(key, None)
        return None

    def _cache_set(self, connection_id: str, provider: str, payload: CloudTokenPayload) -> None:
        key = (connection_id or '').strip()
        if not key:
            return
        with self._cache_lock:
            self._token_cache[key] = _TokenCacheItem(
                provider=(provider or '').strip().lower(),
                access_token=payload.access_token,
                token_type=payload.token_type or 'Bearer',
                expires_at=payload.expires_at,
            )

    @staticmethod
    def _validate_required_credentials(*, tenant_id: str, client_id: str, client_secret: str) -> tuple[str, str, str]:
        tid = (tenant_id or '').strip()
        cid = (client_id or '').strip()
        csec = (client_secret or '').strip()
        if not tid or not cid or not csec:
            raise_error(ErrorCodes.CLOUD_CREDENTIAL_INVALID, extra_msg='tenant_id/client_id/client_secret are required')
        return tid, cid, csec

    @staticmethod
    def _new_connection_id() -> str:
        return f'conn_{uuid.uuid4().hex}'

    @staticmethod
    def _encrypt_payload(payload: dict[str, Any], *, field_name: str) -> str:
        try:
            return encrypt_json(payload)
        except RuntimeError as exc:
            raise_error(ErrorCodes.CLOUD_CRYPTO_UNAVAILABLE, extra_msg=_truncate_error(exc))
        except Exception as exc:
            raise_error(
                ErrorCodes.CLOUD_CREDENTIAL_INVALID,
                extra_msg=f'{field_name} encrypt failed: {_truncate_error(exc)}',
            )

    @staticmethod
    def _decrypt_payload(ciphertext: str, *, field_name: str) -> dict[str, Any]:
        try:
            return decrypt_json(ciphertext)
        except RuntimeError as exc:
            raise_error(ErrorCodes.CLOUD_CRYPTO_UNAVAILABLE, extra_msg=_truncate_error(exc))
        except Exception as exc:
            raise_error(
                ErrorCodes.CLOUD_CREDENTIAL_INVALID,
                extra_msg=f'{field_name} decrypt failed: {_truncate_error(exc)}',
            )

    def _create_connection_record(
        self,
        *,
        provider: str,
        tenant_id: str,
        auth_mode: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str = '',
        scope: str = '',
        provider_options: dict[str, Any] | None = None,
        oauth_state: str = '',
        oauth_state_expires_at: datetime | None = None,
    ) -> str:
        connection_id = self._new_connection_id()
        credential = {
            'client_id': client_id,
            'client_secret': client_secret,
            'redirect_uri': (redirect_uri or '').strip(),
            'scope': (scope or '').strip(),
            'provider_options': provider_options or {},
        }
        auth_state_payload = {
            'oauth_state': (oauth_state or '').strip(),
            'oauth_state_expires_at': _iso(oauth_state_expires_at),
            'access_token': '',
            'access_expires_at': '',
            'refresh_token': '',
            'token_type': 'Bearer',
        }
        with SessionLocal() as db:
            CloudAuthConnectionRepository.create(
                db,
                connection_id=connection_id,
                tenant_id=tenant_id,
                provider=(provider or '').strip().lower(),
                auth_mode=auth_mode,
                credential_ciphertext=self._encrypt_payload(credential, field_name='credential'),
                auth_state_ciphertext=self._encrypt_payload(auth_state_payload, field_name='auth_state'),
                status='ACTIVE',
                last_error='',
            )
        return connection_id

    def create_connection(
        self,
        *,
        provider: str,
        tenant_id: str,
        auth_mode: str,
        client_id: str,
        client_secret: str,
        provider_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        provider_impl = self._provider(provider)
        mode = self._validate_auth_mode(auth_mode)
        if mode == 'oauth_user':
            raise_error(ErrorCodes.CLOUD_AUTH_MODE_INVALID, extra_msg='oauth_user should use oauth/authorize-url')
        tid, cid, csec = self._validate_required_credentials(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
        )
        connection_id = self._create_connection_record(
            provider=provider_impl.provider_name(),
            tenant_id=tid,
            auth_mode=mode,
            client_id=cid,
            client_secret=csec,
            provider_options=provider_options,
        )
        return {
            'connection_id': connection_id,
            'tenant_id': tid,
            'provider': provider_impl.provider_name(),
            'auth_mode': mode,
            'status': 'ACTIVE',
        }

    def create_authorize_url(
        self,
        *,
        provider: str,
        tenant_id: str,
        auth_mode: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        scope: str | None = None,
        state: str | None = None,
        provider_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        provider_impl = self._provider(provider)
        mode = self._validate_auth_mode(auth_mode)
        if mode != 'oauth_user':
            raise_error(ErrorCodes.CLOUD_AUTH_MODE_INVALID, extra_msg='authorize-url only supports oauth_user')
        tenant_id, client_id, client_secret = self._validate_required_credentials(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
        )
        redirect_uri = (redirect_uri or '').strip()
        if not redirect_uri:
            raise_error(ErrorCodes.CLOUD_CREDENTIAL_INVALID, extra_msg='redirect_uri is required for oauth_user')

        oauth_state = ''
        oauth_state_expires = None
        authorize_url = ''
        scope_value = (scope or '').strip()
        if not scope_value and hasattr(provider_impl, 'default_scope'):
            scope_value = getattr(provider_impl, 'default_scope')()
        oauth_state = (state or '').strip() or secrets.token_urlsafe(18)
        oauth_state_expires = _utcnow() + timedelta(minutes=_OAUTH_STATE_TTL_MINUTES)
        authorize_url = provider_impl.build_authorize_url(
            client_id=client_id,
            redirect_uri=redirect_uri,
            scope=scope_value,
            state=oauth_state,
        )
        connection_id = self._create_connection_record(
            provider=provider_impl.provider_name(),
            tenant_id=tenant_id,
            auth_mode=mode,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=scope_value,
            provider_options=provider_options,
            oauth_state=oauth_state,
            oauth_state_expires_at=oauth_state_expires,
        )

        return {
            'connection_id': connection_id,
            'tenant_id': tenant_id,
            'provider': provider_impl.provider_name(),
            'auth_mode': mode,
            'authorize_url': authorize_url,
            'state': oauth_state,
        }

    def oauth_callback(
        self,
        *,
        provider: str,
        tenant_id: str,
        connection_id: str,
        code: str,
        state: str | None = None,
        redirect_uri: str | None = None,
    ) -> dict[str, Any]:
        provider_impl = self._provider(provider)
        connection_id = (connection_id or '').strip()
        tenant_id = (tenant_id or '').strip()
        code = (code or '').strip()
        if not code:
            raise_error(ErrorCodes.CLOUD_OAUTH_CODE_REQUIRED)

        with SessionLocal() as db:
            row = CloudAuthConnectionRepository.get_by_id(db, connection_id)
            if row is None:
                raise_error(ErrorCodes.CLOUD_CONNECTION_NOT_FOUND)
            if (row.tenant_id or '').strip() != tenant_id:
                raise_error(ErrorCodes.CLOUD_CONNECTION_NOT_FOUND)
            if (row.provider or '').strip().lower() != provider_impl.provider_name():
                raise_error(ErrorCodes.CLOUD_PROVIDER_UNSUPPORTED)
            if (row.auth_mode or '').strip().lower() != 'oauth_user':
                raise_error(ErrorCodes.CLOUD_AUTH_MODE_INVALID, extra_msg='callback only supports oauth_user')

            credential = self._decrypt_payload(row.credential_ciphertext, field_name='credential')
            auth_state_payload = self._decrypt_payload(row.auth_state_ciphertext, field_name='auth_state')
            expected_state = (auth_state_payload.get('oauth_state') or '').strip()
            expected_expire = _parse_dt(auth_state_payload.get('oauth_state_expires_at'))
            incoming_state = (state or '').strip()
            if not expected_state or not incoming_state or incoming_state != expected_state:
                raise_error(ErrorCodes.CLOUD_OAUTH_STATE_INVALID)
            if expected_expire is not None and expected_expire <= _utcnow():
                raise_error(ErrorCodes.CLOUD_OAUTH_STATE_INVALID)

            effective_redirect_uri = (redirect_uri or '').strip() or (credential.get('redirect_uri') or '').strip()
            if not effective_redirect_uri:
                raise_error(ErrorCodes.CLOUD_CREDENTIAL_INVALID, extra_msg='redirect_uri is required')

            token = provider_impl.exchange_code(
                client_id=(credential.get('client_id') or '').strip(),
                client_secret=(credential.get('client_secret') or '').strip(),
                code=code,
                redirect_uri=effective_redirect_uri,
            )
            if not token.access_token:
                raise_error(ErrorCodes.CLOUD_TOKEN_UNAVAILABLE, extra_msg='empty access_token')

            auth_state_payload.update({
                'oauth_state': '',
                'oauth_state_expires_at': '',
                'access_token': token.access_token,
                'access_expires_at': _iso(token.expires_at),
                'refresh_token': token.refresh_token or '',
                'token_type': token.token_type or 'Bearer',
            })
            if redirect_uri:
                credential['redirect_uri'] = effective_redirect_uri
                row.credential_ciphertext = self._encrypt_payload(credential, field_name='credential')

            row.auth_state_ciphertext = self._encrypt_payload(auth_state_payload, field_name='auth_state')
            row.status = 'ACTIVE'
            row.last_error = ''
            CloudAuthConnectionRepository.save(db, row)

        self._cache_set(connection_id, provider_impl.provider_name(), token)
        return {
            'connection_id': connection_id,
            'tenant_id': tenant_id,
            'provider': provider_impl.provider_name(),
            'status': 'ACTIVE',
            'expires_at': token.expires_at,
            'refresh_token_bound': bool((token.refresh_token or '').strip()),
        }

    def get_connection(self, connection_id: str) -> dict[str, Any]:
        with SessionLocal() as db:
            row = CloudAuthConnectionRepository.get_by_id(db, connection_id)
            if row is None:
                raise_error(ErrorCodes.CLOUD_CONNECTION_NOT_FOUND)
            return {
                'connection_id': row.connection_id,
                'tenant_id': row.tenant_id,
                'provider': row.provider,
                'auth_mode': row.auth_mode,
                'status': row.status,
                'last_error': row.last_error or '',
                'created_at': row.created_at,
                'updated_at': row.updated_at,
            }

    def _refresh_oauth_user_token(
        self,
        *,
        provider_impl: CloudOAuthProvider,
        credential: dict[str, Any],
        auth_state_payload: dict[str, Any],
    ) -> CloudTokenPayload:
        access_token = (auth_state_payload.get('access_token') or '').strip()
        expires_at = _parse_dt(auth_state_payload.get('access_expires_at'))
        if self._is_token_valid(access_token, expires_at):
            return CloudTokenPayload(
                access_token=access_token,
                expires_at=expires_at,
                refresh_token=(auth_state_payload.get('refresh_token') or '').strip(),
                token_type=(auth_state_payload.get('token_type') or 'Bearer').strip() or 'Bearer',
            )

        refresh_token = (auth_state_payload.get('refresh_token') or '').strip()
        if not refresh_token:
            raise_error(ErrorCodes.CLOUD_TOKEN_UNAVAILABLE, extra_msg='refresh_token is missing')
        refreshed = provider_impl.refresh_access_token(
            client_id=(credential.get('client_id') or '').strip(),
            client_secret=(credential.get('client_secret') or '').strip(),
            refresh_token=refresh_token,
        )
        if not refreshed.access_token:
            raise_error(ErrorCodes.CLOUD_TOKEN_UNAVAILABLE, extra_msg='provider returned empty access_token')
        return refreshed

    def get_access_token(self, connection_id: str) -> dict[str, Any]:
        connection_id = (connection_id or '').strip()
        if not connection_id:
            raise_error(ErrorCodes.CLOUD_CONNECTION_NOT_FOUND)

        cached = self._cache_get(connection_id)
        if cached is not None:
            return {
                'connection_id': connection_id,
                'provider': cached.provider,
                'access_token': cached.access_token,
                'token_type': cached.token_type,
                'expires_at': cached.expires_at,
                'status': 'ACTIVE',
            }

        with SessionLocal() as db:
            row = CloudAuthConnectionRepository.get_by_id(db, connection_id)
            if row is None:
                raise_error(ErrorCodes.CLOUD_CONNECTION_NOT_FOUND)
            provider_impl = self._provider(row.provider)
            credential = self._decrypt_payload(row.credential_ciphertext, field_name='credential')
            auth_state_payload = self._decrypt_payload(row.auth_state_ciphertext, field_name='auth_state')

            try:
                mode = (row.auth_mode or '').strip().lower()
                token_payload: CloudTokenPayload
                if mode == 'oauth_user':
                    token_payload = self._refresh_oauth_user_token(
                        provider_impl=provider_impl,
                        credential=credential,
                        auth_state_payload=auth_state_payload,
                    )
                    auth_state_payload.update({
                        'access_token': token_payload.access_token,
                        'access_expires_at': _iso(token_payload.expires_at),
                        'refresh_token': token_payload.refresh_token or auth_state_payload.get('refresh_token') or '',
                        'token_type': token_payload.token_type or 'Bearer',
                    })
                    row.auth_state_ciphertext = self._encrypt_payload(auth_state_payload, field_name='auth_state')
                elif mode in {'tenant', 'service_account'}:
                    token_payload = provider_impl.acquire_tenant_access_token(
                        client_id=(credential.get('client_id') or '').strip(),
                        client_secret=(credential.get('client_secret') or '').strip(),
                    )
                else:
                    raise_error(ErrorCodes.CLOUD_AUTH_MODE_INVALID, extra_msg=row.auth_mode)
            except AppException:
                raise
            except Exception as exc:
                row.status = 'ERROR'
                row.last_error = _truncate_error(exc)
                CloudAuthConnectionRepository.save(db, row)
                raise_error(ErrorCodes.CLOUD_TOKEN_UNAVAILABLE, extra_msg=_truncate_error(exc))

            row.status = 'ACTIVE'
            row.last_error = ''
            CloudAuthConnectionRepository.save(db, row)

        self._cache_set(connection_id, row.provider, token_payload)
        return {
            'connection_id': connection_id,
            'provider': row.provider,
            'access_token': token_payload.access_token,
            'token_type': token_payload.token_type or 'Bearer',
            'expires_at': token_payload.expires_at,
            'status': row.status,
        }


cloud_oauth_service = CloudOAuthService()
