"""Auth commands: register, login, logout, whoami."""

import argparse
import getpass
import sys

from cli import credentials
from cli.client import (
    ApiError,
    _try_refresh,
    auth_request,
    print_json,
    raw_request,
    resolve_server_url,
)
from cli.config import AUTH_API_PREFIX


def _prompt(label: str) -> str:
    """Read input, failing fast in non-interactive (non-TTY) mode."""
    if not sys.stdin.isatty():
        print(
            f'Error: {label} required '
            '(pass via CLI flag in non-interactive mode)',
            file=sys.stderr,
        )
        sys.exit(1)
    return input(f'{label}: ').strip()


def _prompt_password(label: str = 'Password') -> str:
    if not sys.stdin.isatty():
        print(
            f'Error: {label} required '
            '(pass via -p flag in non-interactive mode)',
            file=sys.stderr,
        )
        sys.exit(1)
    return getpass.getpass(f'{label}: ')


def cmd_register(args: argparse.Namespace) -> int:
    server = resolve_server_url(args.server)
    username = args.username or _prompt('Username')
    if not username:
        print('Username is required.', file=sys.stderr)
        return 1

    password = args.password or _prompt_password()
    if not password:
        print('Password is required.', file=sys.stderr)
        return 1
    # When the password is passed via -p/--password (non-interactive), treat
    # it as already confirmed; confirm-prompt is only meaningful when the
    # user types the password twice at the TTY.
    if not args.password:
        confirm = _prompt_password('Confirm password')
        if password != confirm:
            print('Passwords do not match.', file=sys.stderr)
            return 1
    confirm = password

    url = f'{server}{AUTH_API_PREFIX}/register'
    payload = {
        'username': username,
        'password': password,
        'confirm_password': confirm,
    }
    if args.email:
        payload['email'] = args.email

    data = raw_request('POST', url, payload=payload)

    if getattr(args, 'as_json', False):
        print_json(data)
    else:
        print(
            f'Registered successfully.  user_id={data.get("user_id")}  '
            f'role={data.get("role")}'
        )

    # auto-login after registration
    if not args.no_login:
        return _do_login(server, username, password, as_json=getattr(args, 'as_json', False))
    return 0


def _do_login(server: str, username: str, password: str, *,
              as_json: bool = False) -> int:
    url = f'{server}{AUTH_API_PREFIX}/login'
    data = raw_request('POST', url, payload={
        'username': username, 'password': password,
    })
    access_token = data.get('access_token')
    refresh_token = data.get('refresh_token')
    if not access_token or not refresh_token:
        print(
            'Error: login response missing token fields.',
            file=sys.stderr,
        )
        return 1
    creds = {
        'server_url': server,
        'username': username,
        'access_token': access_token,
        'refresh_token': refresh_token,
        'expires_in': data.get('expires_in', 0),
        'role': data.get('role'),
        'tenant_id': data.get('tenant_id'),
    }
    credentials.save(creds)

    if as_json:
        print_json({
            'server': server,
            'role': data.get('role'),
            'tenant_id': data.get('tenant_id'),
        })
    else:
        print(f'Logged in as {username} (role={data.get("role")})')
    return 0


def cmd_login(args: argparse.Namespace) -> int:
    server = resolve_server_url(args.server)
    username = args.username or _prompt('Username')
    if not username:
        print('Username is required.', file=sys.stderr)
        return 1

    password = args.password or _prompt_password()
    if not password:
        print('Password is required.', file=sys.stderr)
        return 1

    return _do_login(server, username, password, as_json=getattr(args, 'as_json', False))


def cmd_logout(args: argparse.Namespace) -> int:
    creds = credentials.load()
    if creds and creds.get('refresh_token'):
        server = resolve_server_url(args.server)
        refresh_token = creds['refresh_token']

        def _revoke(access_token: str) -> None:
            raw_request(
                'POST',
                f'{server}{AUTH_API_PREFIX}/logout',
                payload={'refresh_token': refresh_token},
                headers={'Authorization': f'Bearer {access_token}'},
            )

        token = creds.get('access_token')
        # Best-effort server-side revocation.  We intentionally do not go
        # through auth_request here (its SystemExit on expired sessions
        # would swallow local clear-creds); but we still need to handle the
        # common case of an expired access token + valid refresh token, so
        # on HTTP 401 we refresh once and retry the revocation.
        try:
            if token:
                _revoke(token)
        except ApiError as exc:
            if exc.is_http_error and exc.status_code == 401:
                try:
                    if _try_refresh(server):
                        refreshed = credentials.access_token()
                        if refreshed:
                            _revoke(refreshed)
                except (ApiError, RuntimeError):
                    pass
            # else: non-401 server error — swallow for best-effort revoke
        except RuntimeError:
            pass
    credentials.clear()
    print('Logged out.')
    return 0


def cmd_whoami(args: argparse.Namespace) -> int:
    data = auth_request('GET', f'{AUTH_API_PREFIX}/me', server=args.server)
    if args.as_json:
        print_json(data)
    else:
        print(
            f'user_id={data.get("user_id")}  '
            f'username={data.get("username")}  '
            f'role={data.get("role")}  '
            f'status={data.get("status")}'
        )
    return 0
