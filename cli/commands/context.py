"""Context commands: use, status, config."""

import argparse
import sys

from cli import context, credentials
from cli.client import print_json, resolve_server_url


# ---------------------------------------------------------------------------
# use — set default dataset
# ---------------------------------------------------------------------------

def cmd_use(args: argparse.Namespace) -> int:
    context.set_key('dataset', args.dataset_id)
    print(f'Active dataset set to {args.dataset_id}')
    return 0


# ---------------------------------------------------------------------------
# status — show current context
# ---------------------------------------------------------------------------

def cmd_status(args: argparse.Namespace) -> int:
    creds = credentials.load()
    cfg = context.load_config()

    info = {
        'server': resolve_server_url(),
        'logged_in': creds is not None,
        'username': (creds or {}).get('username'),
        'dataset': cfg.get('dataset'),
        'algo_url': cfg.get('algo_url'),
        'algo_dataset': cfg.get('algo_dataset'),
    }
    # Add user info from creds if available
    if creds:
        info['username'] = (
            creds.get('username')
            or creds.get('tenant_id')
            or creds.get('role')
        )
        info['role'] = creds.get('role')
        info['token_expired'] = credentials.is_token_expired()

    if getattr(args, 'as_json', False):
        print_json(info)
        return 0

    server = info['server']
    print(f'Server:        {server}')
    if info['logged_in']:
        print(f'Logged in:     yes (role={info.get("role", "?")})')
        if info.get('token_expired'):
            print('  (token expired, will auto-refresh on next request)')
    else:
        print('Logged in:     no')
    ds = info['dataset']
    print(f'Dataset:       {ds or "(not set)"}')
    algo_url = info['algo_url']
    algo_ds = info['algo_dataset']
    if algo_url or algo_ds:
        print(f'Algo URL:      {algo_url or "(default)"}')
        print(f'Algo dataset:  {algo_ds or "(default)"}')
    return 0


# ---------------------------------------------------------------------------
# config set / get / list
# ---------------------------------------------------------------------------

def cmd_config(args: argparse.Namespace) -> int:
    action = args.config_action

    if action == 'list':
        cfg = context.load_config()
        if getattr(args, 'as_json', False):
            print_json(cfg)
            return 0
        if not cfg:
            print('No config values set.')
            return 0
        for key, value in sorted(cfg.items()):
            desc = context.KNOWN_KEYS.get(key, '')
            suffix = f'  # {desc}' if desc else ''
            print(f'{key} = {value}{suffix}')
        return 0

    if action == 'get':
        value = context.get(args.key)
        if value is None:
            print(f'{args.key}: (not set)', file=sys.stderr)
            return 1
        print(value)
        return 0

    if action == 'set':
        context.set_key(args.key, args.value)
        print(f'{args.key} = {args.value}')
        return 0

    if action == 'unset':
        context.unset_key(args.key)
        print(f'{args.key} unset')
        return 0

    return 1
