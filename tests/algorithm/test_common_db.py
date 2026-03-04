"""
Unit tests for algorithm/common/db.py (parse_db_url, get_doc_task_db_config).
No external deps - pure functions.
"""
import os
import pytest

from common.db import parse_db_url, get_doc_task_db_config


def test_parse_db_url_empty():
    assert parse_db_url(None) is None
    assert parse_db_url('') is None
    assert parse_db_url('   ') is None


def test_parse_db_url_postgres():
    url = 'postgresql+psycopg://user:pass@host:5432/mydb'
    r = parse_db_url(url)
    assert r is not None
    assert r['db_type'] == 'postgresql'
    assert r['user'] == 'user'
    assert r['password'] == 'pass'
    assert r['host'] == 'host'
    assert r['port'] == 5432
    assert r['db_name'] == 'mydb'


def test_parse_db_url_postgres_default_port():
    url = 'postgresql://u:p@localhost/db'
    r = parse_db_url(url)
    assert r['port'] == 5432


def test_parse_db_url_mysql():
    url = 'mysql://u:p@host:3306/app'
    r = parse_db_url(url)
    assert r['db_type'] == 'mysql'
    assert r['port'] == 3306


def test_parse_db_url_urlencoded_password():
    url = 'postgresql://u:pass%40word@h/db'
    r = parse_db_url(url)
    assert r['password'] == 'pass@word'


def test_parse_db_url_no_host():
    assert parse_db_url('postgresql:///db') is None


def test_get_doc_task_db_config_unset(monkeypatch):
    monkeypatch.delenv('LAZYRAG_DOC_TASK_DATABASE_URL', raising=False)
    assert get_doc_task_db_config() is None


def test_get_doc_task_db_config_set(monkeypatch):
    monkeypatch.setenv('LAZYRAG_DOC_TASK_DATABASE_URL', 'postgresql://u:p@localhost:5432/tasks')
    r = get_doc_task_db_config()
    assert r is not None
    assert r['db_name'] == 'tasks'
