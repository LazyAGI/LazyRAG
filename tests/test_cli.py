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
from cli import context as ctx_mod  # noqa: E402
from cli.client import (  # noqa: E402
    ApiError, build_multipart_body, build_multipart_file, raw_request,
)
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

    def test_build_multipart_file_streams_from_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'test.txt'
            path.write_text('hello-stream', encoding='utf-8')

            handle, headers = build_multipart_file(
                fields={'key': 'value'},
                file_field='file',
                filename='test.txt',
                source_path=str(path),
            )
            try:
                body = handle.read()
            finally:
                handle.close()

        self.assertIn('multipart/form-data', headers['Content-Type'])
        self.assertEqual(headers['Content-Length'], str(len(body)))
        self.assertIn(b'hello-stream', body)
        self.assertIn(b'test.txt', body)


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
        data = creds_mod.load()
        data['saved_at'] = time.time() - 100
        creds_mod.CREDENTIALS_FILE.write_text(
            json.dumps(data), encoding='utf-8',
        )
        self.assertTrue(creds_mod.is_token_expired())


class TestAuthCommands(unittest.TestCase):
    @mock.patch('cli.commands.auth.credentials.save')
    @mock.patch('cli.commands.auth.raw_request')
    def test_login_stores_username(self, mock_raw_request, mock_save):
        from cli.commands import auth as auth_mod

        mock_raw_request.return_value = {
            'access_token': 'access',
            'refresh_token': 'refresh',
            'expires_in': 3600,
            'role': 'user',
            'tenant_id': 'tenant-1',
        }

        result = auth_mod._do_login('http://server', 'alice', 'pw')

        self.assertEqual(result, 0)
        mock_save.assert_called_once_with({
            'server_url': 'http://server',
            'username': 'alice',
            'access_token': 'access',
            'refresh_token': 'refresh',
            'expires_in': 3600,
            'role': 'user',
            'tenant_id': 'tenant-1',
        })


class TestContext(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._orig_dir = ctx_mod.CREDENTIALS_DIR
        self._orig_file = ctx_mod.CONFIG_FILE
        ctx_mod.CREDENTIALS_DIR = Path(self._tmpdir)
        ctx_mod.CONFIG_FILE = Path(self._tmpdir) / 'config.json'

    def tearDown(self):
        ctx_mod.CREDENTIALS_DIR = self._orig_dir
        ctx_mod.CONFIG_FILE = self._orig_file
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_set_and_get(self):
        ctx_mod.set_key('dataset', 'ds1')
        self.assertEqual(ctx_mod.get('dataset'), 'ds1')

    def test_unset(self):
        ctx_mod.set_key('dataset', 'ds1')
        ctx_mod.unset_key('dataset')
        self.assertIsNone(ctx_mod.get('dataset'))

    def test_resolve_dataset_from_cli(self):
        self.assertEqual(ctx_mod.resolve_dataset('cli_ds'), 'cli_ds')

    def test_resolve_dataset_from_config(self):
        ctx_mod.set_key('dataset', 'cfg_ds')
        self.assertEqual(ctx_mod.resolve_dataset(None), 'cfg_ds')

    def test_resolve_dataset_missing_exits(self):
        with self.assertRaises(SystemExit):
            ctx_mod.resolve_dataset(None)

    def test_resolve_algo_url_default(self):
        url = ctx_mod.resolve_algo_url(None)
        self.assertTrue(url.startswith('http'))

    def test_resolve_algo_dataset_default(self):
        self.assertEqual(ctx_mod.resolve_algo_dataset(None), 'general_algo')


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

    def test_login_json(self):
        parser = build_parser()
        args = parser.parse_args(['login', '-u', 'a', '-p', 'b', '--json'])
        self.assertTrue(args.as_json)

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

    def test_upload_no_dataset(self):
        parser = build_parser()
        args = parser.parse_args([
            'upload', '--dir', '/tmp/docs',
        ])
        self.assertIsNone(args.dataset)

    def test_task_list_command(self):
        parser = build_parser()
        args = parser.parse_args(['task-list', '--dataset', 'ds1'])
        self.assertEqual(args.command, 'task-list')

    def test_task_get_command(self):
        parser = build_parser()
        args = parser.parse_args(['task-get', '--dataset', 'ds1', 'tid-123'])
        self.assertEqual(args.command, 'task-get')
        self.assertEqual(args.task_id, 'tid-123')

    def test_kb_delete_command(self):
        parser = build_parser()
        args = parser.parse_args(['kb-delete', '--dataset', 'ds1', '-y'])
        self.assertEqual(args.command, 'kb-delete')
        self.assertEqual(args.dataset, 'ds1')
        self.assertTrue(args.yes)

    def test_doc_list_command(self):
        parser = build_parser()
        args = parser.parse_args([
            'doc-list', '--dataset', 'ds1', '--page-size', '10',
        ])
        self.assertEqual(args.command, 'doc-list')
        self.assertEqual(args.dataset, 'ds1')
        self.assertEqual(args.page_size, 10)

    def test_doc_delete_positional(self):
        parser = build_parser()
        args = parser.parse_args([
            'doc-delete', 'doc1', '-y',
        ])
        self.assertEqual(args.command, 'doc-delete')
        self.assertEqual(args.document, 'doc1')
        self.assertIsNone(args.dataset)

    def test_doc_update_positional(self):
        parser = build_parser()
        args = parser.parse_args([
            'doc-update', 'doc1', '--name', 'New Name',
            '--meta', '{"key":"val"}',
        ])
        self.assertEqual(args.command, 'doc-update')
        self.assertEqual(args.document, 'doc1')
        self.assertEqual(args.name, 'New Name')

    def test_use_command(self):
        parser = build_parser()
        args = parser.parse_args(['use', 'ds_abc'])
        self.assertEqual(args.command, 'use')
        self.assertEqual(args.dataset_id, 'ds_abc')

    def test_status_command(self):
        parser = build_parser()
        args = parser.parse_args(['status', '--json'])
        self.assertEqual(args.command, 'status')
        self.assertTrue(args.as_json)

    def test_config_set(self):
        parser = build_parser()
        args = parser.parse_args(['config', 'set', 'algo_url', 'http://x'])
        self.assertEqual(args.config_action, 'set')
        self.assertEqual(args.key, 'algo_url')
        self.assertEqual(args.value, 'http://x')

    def test_config_get(self):
        parser = build_parser()
        args = parser.parse_args(['config', 'get', 'dataset'])
        self.assertEqual(args.config_action, 'get')
        self.assertEqual(args.key, 'dataset')

    def test_chunk_positional(self):
        parser = build_parser()
        args = parser.parse_args(['chunk', 'doc_xyz', '--dataset', 'ds1'])
        self.assertEqual(args.command, 'chunk')
        self.assertEqual(args.document, 'doc_xyz')
        self.assertEqual(args.dataset, 'ds1')

    def test_retrieve_minimal(self):
        parser = build_parser()
        args = parser.parse_args(['retrieve', 'test query'])
        self.assertEqual(args.query, 'test query')
        self.assertEqual(args.group_name, 'block')
        self.assertEqual(args.topk, 6)
        self.assertIsNone(args.url)


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


class TestKbDeleteCommand(unittest.TestCase):
    @mock.patch('cli.commands.dataset.auth_request')
    @mock.patch('cli.commands.dataset.resolve_dataset', return_value='ds1')
    def test_kb_delete_with_yes(self, mock_resolve, mock_auth):
        from cli.commands import dataset as dataset_mod
        mock_auth.return_value = {}
        args = build_parser().parse_args([
            'kb-delete', '--dataset', 'ds1', '-y',
        ])
        result = dataset_mod.cmd_kb_delete(args)
        self.assertEqual(result, 0)
        self.assertEqual(mock_auth.call_args[0][0], 'DELETE')


class TestDocListCommand(unittest.TestCase):
    @mock.patch('cli.commands.doc.auth_request')
    @mock.patch('cli.commands.doc.resolve_dataset', return_value='ds1')
    def test_doc_list_json(self, mock_resolve, mock_auth):
        from cli.commands import doc as doc_mod
        mock_auth.return_value = {
            'documents': [
                {'document_id': 'd1', 'display_name': 'test.pdf',
                 'status': 'completed', 'segment_count': 5},
            ],
            'total': 1,
        }
        args = build_parser().parse_args([
            'doc-list', '--dataset', 'ds1', '--json',
        ])
        result = doc_mod.cmd_doc_list(args)
        self.assertEqual(result, 0)

    @mock.patch('cli.commands.doc.auth_request')
    @mock.patch('cli.commands.doc.resolve_dataset', return_value='ds1')
    def test_doc_list_table(self, mock_resolve, mock_auth):
        from cli.commands import doc as doc_mod
        mock_auth.return_value = {
            'documents': [
                {'document_id': 'd1', 'display_name': 'a.pdf',
                 'status': 'completed', 'segment_count': 3},
                {'document_id': 'd2', 'display_name': 'b.txt',
                 'status': 'parsing', 'segment_count': 0},
            ],
            'total': 2,
        }
        args = build_parser().parse_args(['doc-list', '--dataset', 'ds1'])
        result = doc_mod.cmd_doc_list(args)
        self.assertEqual(result, 0)


class TestDocDeleteCommand(unittest.TestCase):
    @mock.patch('cli.commands.doc.auth_request')
    @mock.patch('cli.commands.doc.resolve_dataset', return_value='ds1')
    def test_doc_delete_with_yes(self, mock_resolve, mock_auth):
        from cli.commands import doc as doc_mod
        mock_auth.return_value = {}
        args = build_parser().parse_args([
            'doc-delete', 'doc1', '--dataset', 'ds1', '-y',
        ])
        result = doc_mod.cmd_doc_delete(args)
        self.assertEqual(result, 0)
        self.assertEqual(mock_auth.call_args[0][0], 'DELETE')


class TestDocUpdateCommand(unittest.TestCase):
    @mock.patch('cli.commands.doc.auth_request')
    @mock.patch('cli.commands.doc.resolve_dataset', return_value='ds1')
    def test_doc_update_name(self, mock_resolve, mock_auth):
        from cli.commands import doc as doc_mod
        mock_auth.return_value = {'display_name': 'New Name'}
        args = build_parser().parse_args([
            'doc-update', 'doc1', '--dataset', 'ds1',
            '--name', 'New Name',
        ])
        result = doc_mod.cmd_doc_update(args)
        self.assertEqual(result, 0)
        self.assertEqual(mock_auth.call_args[0][0], 'PATCH')

    def test_doc_update_nothing(self):
        from cli.commands import doc as doc_mod
        args = build_parser().parse_args([
            'doc-update', 'doc1', '--dataset', 'ds1',
        ])
        result = doc_mod.cmd_doc_update(args)
        self.assertEqual(result, 1)

    def test_doc_update_bad_json(self):
        from cli.commands import doc as doc_mod
        args = build_parser().parse_args([
            'doc-update', 'doc1', '--dataset', 'ds1',
            '--meta', 'not-json',
        ])
        result = doc_mod.cmd_doc_update(args)
        self.assertEqual(result, 1)


class TestUploadCommand(unittest.TestCase):
    @mock.patch('cli.commands.upload.wait_for_tasks')
    @mock.patch('cli.commands.upload.start_tasks')
    @mock.patch('cli.commands.upload.upload_single_file')
    @mock.patch('cli.commands.upload.collect_files')
    @mock.patch('cli.commands.upload.resolve_dataset', return_value='ds1')
    def test_wait_treats_success_as_success(
        self,
        mock_resolve,
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


class TestChunkCommand(unittest.TestCase):
    def test_chunk_arg_parsing(self):
        parser = build_parser()
        args = parser.parse_args([
            'chunk', 'doc1', '--dataset', 'ds1',
            '--page-size', '50', '--json',
        ])
        self.assertEqual(args.command, 'chunk')
        self.assertEqual(args.document, 'doc1')
        self.assertEqual(args.dataset, 'ds1')
        self.assertEqual(args.page_size, 50)
        self.assertTrue(args.as_json)

    @mock.patch('cli.commands.chunk.auth_request')
    @mock.patch('cli.commands.chunk.resolve_dataset', return_value='ds1')
    def test_chunk_json_output(self, mock_resolve, mock_auth):
        from cli.commands import chunk as chunk_mod
        mock_auth.return_value = {
            'segments': [
                {'segment_id': 'seg1', 'status': 'completed',
                 'word_count': 42, 'content': 'hello world'},
            ],
            'total_size': 1,
        }
        args = build_parser().parse_args([
            'chunk', 'doc1', '--dataset', 'ds1', '--json',
        ])
        result = chunk_mod.cmd_chunk(args)
        self.assertEqual(result, 0)
        mock_auth.assert_called_once_with(
            'GET',
            '/api/core/datasets/ds1/documents/doc1/segments?page_size=20',
            server=None,
        )


class TestRetrieveCommand(unittest.TestCase):
    def test_retrieve_arg_parsing(self):
        parser = build_parser()
        args = parser.parse_args([
            'retrieve', 'what is RAG',
            '--url', 'http://algo:8000',
            '--dataset', 'kb_test',
            '--algo-dataset', 'general_algo',
            '--group-name', 'line',
            '--topk', '10',
            '--similarity', 'bm25',
            '--embed-keys', 'embed1,embed2',
            '--json',
        ])
        self.assertEqual(args.command, 'retrieve')
        self.assertEqual(args.query, 'what is RAG')
        self.assertEqual(args.url, 'http://algo:8000')
        self.assertEqual(args.dataset, 'kb_test')
        self.assertEqual(args.algo_dataset, 'general_algo')
        self.assertEqual(args.group_name, 'line')
        self.assertEqual(args.topk, 10)
        self.assertEqual(args.similarity, 'bm25')
        self.assertEqual(args.embed_keys, 'embed1,embed2')
        self.assertTrue(args.as_json)

    def test_retrieve_defaults(self):
        parser = build_parser()
        args = parser.parse_args(['retrieve', 'test query'])
        self.assertEqual(args.group_name, 'block')
        self.assertEqual(args.topk, 6)
        self.assertEqual(args.similarity, 'cosine')
        self.assertIsNone(args.embed_keys)
        self.assertIsNone(args.config)
        self.assertIsNone(args.algo_dataset)
        self.assertFalse(args.as_json)

    @mock.patch('cli.commands.retrieve.resolve_dataset', return_value='kb_test')
    @mock.patch('cli.commands.retrieve.resolve_algo_dataset', return_value='general_algo')
    @mock.patch('cli.commands.retrieve._run_single_retriever')
    @mock.patch('cli.commands.retrieve._build_document')
    @mock.patch('cli.commands.retrieve._ensure_lazyllm')
    def test_retrieve_calls_single_retriever(
        self, mock_ensure, mock_build_doc, mock_run, mock_resolve_algo, mock_resolve_dataset,
    ):
        from cli.commands import retrieve as retrieve_mod
        mock_build_doc.return_value = mock.MagicMock()
        mock_run.return_value = [
            {'content': 'result text', 'score': 0.95, 'group': 'block'},
        ]
        args = build_parser().parse_args([
            'retrieve', 'hello',
            '--url', 'http://test:8000',
            '--dataset', 'test_ds',
            '--embed-keys', 'key1',
        ])
        result = retrieve_mod.cmd_retrieve(args)
        self.assertEqual(result, 0)
        mock_build_doc.assert_called_once_with('http://test:8000', 'general_algo')
        mock_run.assert_called_once_with(
            mock_build_doc.return_value,
            query='hello',
            filters={'kb_id': 'kb_test'},
            group_name='block',
            topk=6,
            similarity='cosine',
            embed_keys=['key1'],
        )

    @mock.patch('cli.commands.retrieve.resolve_dataset', return_value='kb_cfg')
    @mock.patch('cli.commands.retrieve.resolve_algo_dataset', return_value='general_algo')
    @mock.patch('cli.commands.retrieve._run_config_retrievers')
    @mock.patch('cli.commands.retrieve._build_document')
    @mock.patch('cli.commands.retrieve._ensure_lazyllm')
    @mock.patch('cli.commands.retrieve._find_local_algo_container', return_value=None)
    def test_retrieve_config_mode(
        self,
        mock_find_container,
        mock_ensure,
        mock_build_doc,
        mock_run_cfg,
        mock_resolve_algo,
        mock_resolve_dataset,
    ):
        from cli.commands import retrieve as retrieve_mod
        mock_build_doc.return_value = mock.MagicMock()
        mock_run_cfg.return_value = []
        args = build_parser().parse_args([
            'retrieve', 'query text',
            '--config', '/path/to/models.yaml',
        ])
        result = retrieve_mod.cmd_retrieve(args)
        self.assertEqual(result, 0)
        mock_run_cfg.assert_called_once_with(
            mock_build_doc.return_value,
            'query text',
            {'kb_id': 'kb_cfg'},
            '/path/to/models.yaml',
        )


class TestUseCommand(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._orig_dir = ctx_mod.CREDENTIALS_DIR
        self._orig_file = ctx_mod.CONFIG_FILE
        ctx_mod.CREDENTIALS_DIR = Path(self._tmpdir)
        ctx_mod.CONFIG_FILE = Path(self._tmpdir) / 'config.json'

    def tearDown(self):
        ctx_mod.CREDENTIALS_DIR = self._orig_dir
        ctx_mod.CONFIG_FILE = self._orig_file
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_use_sets_dataset(self):
        from cli.commands import context as context_mod
        args = build_parser().parse_args(['use', 'ds_new'])
        result = context_mod.cmd_use(args)
        self.assertEqual(result, 0)
        self.assertEqual(ctx_mod.get('dataset'), 'ds_new')


class TestConfigCommand(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._orig_dir = ctx_mod.CREDENTIALS_DIR
        self._orig_file = ctx_mod.CONFIG_FILE
        ctx_mod.CREDENTIALS_DIR = Path(self._tmpdir)
        ctx_mod.CONFIG_FILE = Path(self._tmpdir) / 'config.json'

    def tearDown(self):
        ctx_mod.CREDENTIALS_DIR = self._orig_dir
        ctx_mod.CONFIG_FILE = self._orig_file
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_config_set_and_get(self):
        from cli.commands import context as context_mod
        args_set = build_parser().parse_args([
            'config', 'set', 'algo_url', 'http://x',
        ])
        context_mod.cmd_config(args_set)
        self.assertEqual(ctx_mod.get('algo_url'), 'http://x')

    def test_config_unset(self):
        from cli.commands import context as context_mod
        ctx_mod.set_key('algo_url', 'http://x')
        args = build_parser().parse_args(['config', 'unset', 'algo_url'])
        context_mod.cmd_config(args)
        self.assertIsNone(ctx_mod.get('algo_url'))


class TestStatusCommand(unittest.TestCase):
    @mock.patch('cli.commands.context.resolve_server_url', return_value='http://x')
    @mock.patch('cli.commands.context.print_json')
    @mock.patch('cli.commands.context.credentials.is_token_expired', return_value=False)
    @mock.patch('cli.commands.context.credentials.load')
    @mock.patch('cli.commands.context.context.load_config')
    def test_status_prefers_username(
        self,
        mock_load_config,
        mock_load_creds,
        mock_expired,
        mock_print_json,
        mock_resolve_server,
    ):
        from cli.commands import context as context_mod

        mock_load_config.return_value = {'dataset': 'ds1'}
        mock_load_creds.return_value = {
            'username': 'alice',
            'tenant_id': 'tenant-1',
            'role': 'user',
        }

        args = build_parser().parse_args(['status', '--json'])
        result = context_mod.cmd_status(args)

        self.assertEqual(result, 0)
        mock_print_json.assert_called_once_with({
            'server': 'http://x',
            'logged_in': True,
            'username': 'alice',
            'dataset': 'ds1',
            'algo_url': None,
            'algo_dataset': None,
            'role': 'user',
            'token_expired': False,
        })


class TestRetrieveDockerMode(unittest.TestCase):
    @mock.patch('cli.commands.retrieve._print_results')
    @mock.patch('cli.commands.retrieve._run_docker_retrieve')
    @mock.patch('cli.commands.retrieve._find_local_algo_container', return_value='algo-1')
    @mock.patch('cli.commands.retrieve.get_context', return_value=None)
    def test_retrieve_uses_docker_when_no_algo_url(
        self,
        mock_get_context,
        mock_find_container,
        mock_run_docker,
        mock_print_results,
    ):
        from cli.commands import retrieve as retrieve_mod

        mock_run_docker.return_value = [{'content': 'hit'}]
        args = build_parser().parse_args(['retrieve', 'hello'])

        result = retrieve_mod.cmd_retrieve(args)

        self.assertEqual(result, 0)
        mock_run_docker.assert_called_once_with('algo-1', args)
        mock_print_results.assert_called_once_with([{'content': 'hit'}], False)

    @mock.patch('cli.commands.retrieve.get_context', return_value='http://algo:8000')
    @mock.patch('cli.commands.retrieve._run_local_retrieve')
    @mock.patch('cli.commands.retrieve._find_local_algo_container')
    def test_retrieve_prefers_configured_algo_url(
        self,
        mock_find_container,
        mock_run_local,
        mock_get_context,
    ):
        from cli.commands import retrieve as retrieve_mod

        mock_run_local.return_value = []
        args = build_parser().parse_args(['retrieve', 'hello'])

        result = retrieve_mod.cmd_retrieve(args)

        self.assertEqual(result, 0)
        mock_run_local.assert_called_once_with(args)
        mock_find_container.assert_not_called()


if __name__ == '__main__':
    unittest.main()
