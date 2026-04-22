import core.database as database


def test_resolve_database_url_defaults_to_sqlite(monkeypatch):
    monkeypatch.delenv('LAZYRAG_DATABASE_URL', raising=False)

    result = database._resolve_database_url()

    assert isinstance(result, str)
    assert result == 'sqlite:///./app.db'


def test_resolve_database_url_uses_env_value(monkeypatch):
    monkeypatch.setenv('LAZYRAG_DATABASE_URL', 'postgresql+psycopg://user:pass@db/app')

    result = database._resolve_database_url()

    assert isinstance(result, str)
    assert result == 'postgresql+psycopg://user:pass@db/app'


def test_module_configures_sqlite_connect_args_from_database_url():
    if database.DATABASE_URL.startswith('sqlite'):
        assert database.connect_args == {'check_same_thread': False}
    else:
        assert database.connect_args == {}

    assert isinstance(database.connect_args, dict)
    assert database.SessionLocal.kw['autoflush'] is False
    assert database.SessionLocal.kw['autocommit'] is False
