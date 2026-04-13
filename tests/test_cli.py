"""Unit tests for the cli package."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Ensure repo root is on sys.path so ``import cli`` works.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cli import credentials as creds_mod  # noqa: E402
from cli.client import ApiError, build_multipart_body, raw_request  # noqa: E402
from cli.commands import upload as upload_mod  # noqa: E402
from cli.commands.upload import collect_files, parse_extensions  # noqa: E402
from cli.main import build_parser  # noqa: E402


class TestParseExtensions(unittest.TestCase):
    def test_none_returns_none(self):
        self.assertIsNone(parse_extensions(None))
        self.assertIsNone(parse_extensions(''))

    def test_basic(self):
        result = parse_extensions('pdf,docx,TXT')
        self.assertEqual(result, {'pdf', 'docx', 'txt'})

    def test_strips_dots(self):
        result = parse_extensions('.pdf, .docx')
        self.assertEqual(result, {'pdf', 'docx'})


class TestCollectFiles(unittest.TestCase):
    def test_skips_hidden_and_filters_extensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'keep.txt').write_text('k')
            (root / 'skip.pdf').write_text('s')
            (root / '.hidden.txt').write_text('h')
            nested = root / 'nested'
            nested.mkdir()
            (nested / 'note.txt').write_text('n')
            hidden_dir = root / '.secret'
            hidden_dir.mkdir()
            (hidden_dir / 'secret.txt').write_text('x')

            entries = collect_files(str(root), extensions={'txt'})

        relatives = sorted(rel for _, rel in entries)
        self.assertEqual(relatives, ['keep.txt', 'nested/note.txt'])

    def test_non_recursive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'a.txt').write_text('a')
            nested = root / 'sub'
            nested.mkdir()
            (nested / 'b.txt').write_text('b')

            entries = collect_files(str(root), recursive=False)

        relatives = [rel for _, rel in entries]
        self.assertEqual(relatives, ['a.txt'])


class TestBuildMultipartBody(unittest.TestCase):
    def test_produces_valid_multipart(self):
        body, headers = build_multipart_body(
            fields={'key': 'value'},
            file_field='file',
            filename='test.txt',
            file_content=b'hello',
        )
        ct = headers['Content-Type']
        self.assertIn('multipart/form-data', ct)
        self.assertIn(b'hello', body)
        self.assertIn(b'test.txt', body)
        self.assertIn(b'key', body)
        self.assertIn(b'value', body)


class TestCredentials(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._orig_dir = creds_mod.CREDENTIALS_DIR
        self._orig_file = creds_mod.CREDENTIALS_FILE
        creds_mod.CREDENTIALS_DIR = Path(self._tmpdir)
        creds_mod.CREDENTIALS_FILE = Path(self._tmpdir) / 'credentials.json'

    def tearDown(self):
        creds_mod.CREDENTIALS_DIR = self._orig_dir
        creds_mod.CREDENTIALS_FILE = self._orig_file
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_save_and_load(self):
        creds_mod.save({'access_token': 'tok123', 'server_url': 'http://x'})
        data = creds_mod.load()
        self.assertIsNotNone(data)
        self.assertEqual(data['access_token'], 'tok123')
        self.assertEqual(data['server_url'], 'http://x')
        self.assertIn('saved_at', data)

    def test_clear(self):
        creds_mod.save({'access_token': 'tok'})
        creds_mod.clear()
        self.assertIsNone(creds_mod.load())

    def test_access_token(self):
        creds_mod.save({'access_token': 'abc'})
        self.assertEqual(creds_mod.access_token(), 'abc')

    def test_load_returns_none_when_missing(self):
        self.assertIsNone(creds_mod.load())

    def test_is_token_expired(self):
        import time
        creds_mod.save({
            'access_token': 'x',
            'expires_in': 10,
            'saved_at': time.time() - 100,
        })
        # override saved_at via direct write to simulate old token
        data = creds_mod.load()
        data['saved_at'] = time.time() - 100
        creds_mod.CREDENTIALS_FILE.write_text(
            json.dumps(data), encoding='utf-8',
        )
        self.assertTrue(creds_mod.is_token_expired())


class TestBuildParser(unittest.TestCase):
    def test_register_command(self):
        parser = build_parser()
        args = parser.parse_args(['register', '-u', 'alice', '-p', 'pass'])
        self.assertEqual(args.command, 'register')
        self.assertEqual(args.username, 'alice')

    def test_login_command(self):
        parser = build_parser()
        args = parser.parse_args(['login', '-u', 'bob', '-p', 'pw'])
        self.assertEqual(args.command, 'login')
        self.assertEqual(args.username, 'bob')

    def test_kb_create_command(self):
        parser = build_parser()
        args = parser.parse_args([
            'kb-create', '--name', 'My KB', '--desc', 'test',
        ])
        self.assertEqual(args.command, 'kb-create')
        self.assertEqual(args.name, 'My KB')
        self.assertEqual(args.desc, 'test')

    def test_kb_list_command(self):
        parser = build_parser()
        args = parser.parse_args(['kb-list', '--json'])
        self.assertEqual(args.command, 'kb-list')
        self.assertTrue(args.as_json)

    def test_upload_command(self):
        parser = build_parser()
        args = parser.parse_args([
            'upload', '--dataset', 'ds1', '--dir', '/tmp/docs',
            '--extensions', 'pdf,docx', '--wait',
        ])
        self.assertEqual(args.command, 'upload')
        self.assertEqual(args.dataset, 'ds1')
        self.assertEqual(args.directory, '/tmp/docs')
        self.assertTrue(args.wait)

    def test_task_list_command(self):
        parser = build_parser()
        args = parser.parse_args(['task-list', '--dataset', 'ds1'])
        self.assertEqual(args.command, 'task-list')

    def test_task_get_command(self):
        parser = build_parser()
        args = parser.parse_args(['task-get', '--dataset', 'ds1', 'tid-123'])
        self.assertEqual(args.command, 'task-get')
        self.assertEqual(args.task_id, 'tid-123')


class TestApiError(unittest.TestCase):
    def test_str(self):
        err = ApiError(404, 'not found', {'detail': 'gone'})
        self.assertEqual(str(err), 'not found')
        self.assertEqual(err.status_code, 404)
        self.assertEqual(err.payload, {'detail': 'gone'})


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode('utf-8')

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class TestRawRequest(unittest.TestCase):
    @mock.patch('cli.client.request.urlopen')
    def test_unwraps_auth_success_envelope(self, mock_urlopen):
        mock_urlopen.return_value = _FakeResponse({
            'code': 200,
            'message': 'success',
            'data': {'user_id': 'u1', 'role': 'user'},
        })

        data = raw_request('POST', 'http://example.test/auth/register')

        self.assertEqual(data, {'user_id': 'u1', 'role': 'user'})

    @mock.patch('cli.client.request.urlopen')
    def test_unwraps_core_success_envelope(self, mock_urlopen):
        mock_urlopen.return_value = _FakeResponse({
            'code': 0,
            'message': 'ok',
            'data': {'datasets': [{'dataset_id': 'ds1'}]},
        })

        data = raw_request('GET', 'http://example.test/api/core/datasets')

        self.assertEqual(data, {'datasets': [{'dataset_id': 'ds1'}]})

    @mock.patch('cli.client.request.urlopen')
    def test_raises_for_non_zero_error_envelope(self, mock_urlopen):
        mock_urlopen.return_value = _FakeResponse({
            'code': 40001,
            'message': 'bad request',
            'data': {'reason': 'invalid'},
        })

        with self.assertRaises(ApiError) as ctx:
            raw_request('GET', 'http://example.test/fail')

        self.assertEqual(ctx.exception.status_code, 40001)
        self.assertEqual(str(ctx.exception), 'bad request')


class TestUploadCommand(unittest.TestCase):
    @mock.patch('cli.commands.upload.wait_for_tasks')
    @mock.patch('cli.commands.upload.start_tasks')
    @mock.patch('cli.commands.upload.upload_single_file')
    @mock.patch('cli.commands.upload.collect_files')
    def test_wait_treats_success_as_success(
        self,
        mock_collect_files,
        mock_upload_single_file,
        mock_start_tasks,
        mock_wait_for_tasks,
    ):
        mock_collect_files.return_value = [('/tmp/doc.txt', 'doc.txt')]
        mock_upload_single_file.return_value = {
            'task_id': 'task-1',
            'task_state': 'CREATING',
        }
        mock_start_tasks.return_value = {
            'started_count': 1,
            'failed_count': 0,
            'tasks': [{'task_id': 'task-1', 'status': 'STARTED'}],
        }
        mock_wait_for_tasks.return_value = {
            'task-1': {'task_state': 'SUCCESS', 'err_msg': 'success'},
        }

        args = build_parser().parse_args([
            'upload',
            '--dataset', 'ds1',
            '--dir', '/tmp/docs',
            '--wait',
        ])

        result = upload_mod.cmd_upload(args)

        self.assertEqual(result, 0)


if __name__ == '__main__':
    unittest.main()
