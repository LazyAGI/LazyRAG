#!/usr/bin/env python3
"""Minimal HTTP server that mocks the core remote-fs API for integration tests.

Usage:
    python scripts/mock_remote_fs_server.py \
        --host 127.0.0.1 --port 9876 \
        --root /tmp/mock-fs \
        --seed-demo-data
"""
import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


def _ok(data):
    return json.dumps({'code': 0, 'data': data}).encode()


def _err(message, code=1):
    return json.dumps({'code': code, 'message': message}).encode()


class RemoteFSHandler(BaseHTTPRequestHandler):
    root: Path  # set on the class before serving

    def log_message(self, fmt, *args):  # silence access log
        pass

    def _send(self, body: bytes, status: int = 200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        path_param = qs.get('path', [''])[0]
        detail = qs.get('detail', ['true'])[0].lower() == 'true'

        endpoint = parsed.path.rstrip('/')

        if endpoint == '/remote-fs/exists':
            target = self.root / path_param if path_param else self.root
            self._send(_ok({'exists': target.exists()}))

        elif endpoint == '/remote-fs/info':
            target = self.root / path_param if path_param else self.root
            if not target.exists():
                self._send(_err(f'path does not exist: {path_param}'), 200)
                return
            self._send(_ok({
                'name': path_param,
                'type': 'directory' if target.is_dir() else 'file',
                'size': target.stat().st_size if target.is_file() else 0,
            }))

        elif endpoint == '/remote-fs/list':
            target = self.root / path_param if path_param else self.root
            if not target.exists():
                self._send(_err(f'path does not exist: {path_param}'), 200)
                return
            entries = []
            names = []
            for child in sorted(target.iterdir()):
                # Return the full path from root (not just the basename)
                rel = str(child.relative_to(self.root))
                names.append(rel)
                if detail:
                    entries.append({
                        'name': rel,
                        'type': 'directory' if child.is_dir() else 'file',
                        'size': child.stat().st_size if child.is_file() else 0,
                    })
            self._send(_ok({'entries': entries, 'names': names}))

        elif endpoint == '/remote-fs/content':
            target = self.root / path_param if path_param else self.root
            if not target.exists() or not target.is_file():
                body = _err(f'file not found: {path_param}')
                self.send_response(404)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            content = target.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'application/octet-stream')
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        else:
            body = _err(f'unknown endpoint: {endpoint}', 404)
            self._send(body, 404)


def _seed_demo_data(root: Path):
    """Create the demo skill tree expected by integration tests."""
    # skills/writing/example/skill.md
    example_dir = root / 'skills' / 'writing' / 'example'
    example_dir.mkdir(parents=True, exist_ok=True)
    (example_dir / 'SKILL.md').write_text(
        '---\nname: example\ncategory: writing\ndescription: A demo skill for testing.\n---\n# Example Skill\n\nThis is a demo skill for testing.\n',
        encoding='utf-8',
    )
    # skills/writing/example/references/examples/daily-update.md
    ref_dir = example_dir / 'references' / 'examples'
    ref_dir.mkdir(parents=True, exist_ok=True)
    (ref_dir / 'daily-update.md').write_text(
        '# Daily Update\n\nCompleted API integration and validated the smoke test.\n',
        encoding='utf-8',
    )
    # skills/ops/deploy-checklist/SKILL.md
    ops_dir = root / 'skills' / 'ops' / 'deploy-checklist'
    ops_dir.mkdir(parents=True, exist_ok=True)
    (ops_dir / 'SKILL.md').write_text(
        '---\nname: deploy-checklist\ncategory: ops\ndescription: Steps to deploy safely.\n---\n# Deploy Checklist\n\nSteps to deploy safely.\n',
        encoding='utf-8',
    )


def main():
    parser = argparse.ArgumentParser(description='Mock remote-fs HTTP server')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=9876)
    parser.add_argument('--root', required=True, help='Root directory to serve')
    parser.add_argument('--seed-demo-data', action='store_true',
                        help='Populate root with demo skill data')
    args = parser.parse_args()

    root = Path(args.root)
    root.mkdir(parents=True, exist_ok=True)

    if args.seed_demo_data:
        _seed_demo_data(root)

    RemoteFSHandler.root = root
    server = HTTPServer((args.host, args.port), RemoteFSHandler)
    print(f'mock remote-fs server listening on {args.host}:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
