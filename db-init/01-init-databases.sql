-- 初始化多个业务数据库与额外应用账号。
-- 该脚本会在 Postgres 容器首次启动、数据目录为空时自动执行。

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app') THEN
    CREATE ROLE app LOGIN CREATEDB PASSWORD 'app';
  ELSE
    ALTER ROLE app WITH LOGIN CREATEDB PASSWORD 'app';
  END IF;
END
$$;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'authservice') THEN
    CREATE DATABASE authservice;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'core') THEN
    CREATE DATABASE core;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'doc_task') THEN
    CREATE DATABASE doc_task;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'app') THEN
    CREATE DATABASE app OWNER app;
  END IF;
END
$$;

