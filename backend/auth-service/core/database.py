import os
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker


def _resolve_database_url() -> str:
    # Docker-compose / local dev convention: provide full SQLAlchemy URL via env var.
    # Example: postgresql+psycopg://user:pass@db:5432/app
    return os.environ.get('LAZYRAG_DATABASE_URL') or 'sqlite:///./app.db'


DATABASE_URL = _resolve_database_url()
connect_args = {'check_same_thread': False} if DATABASE_URL.startswith('sqlite') else {}

engine: Engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
