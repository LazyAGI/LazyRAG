-- 初始化多个业务数据库。
-- 该脚本会在 Postgres 容器首次启动、数据目录为空时自动执行。

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
END
$$;

