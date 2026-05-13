-- 初始化多个业务数据库与额外应用账号。
-- 该脚本会在 Postgres 容器首次启动、数据目录为空时自动执行。
-- 注意：CREATE DATABASE 不能放在 DO/函数/事务块中执行，因此这里使用 psql 的 \gexec。

SELECT 'CREATE ROLE app LOGIN CREATEDB PASSWORD ''app'''
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app')
\gexec

ALTER ROLE app WITH LOGIN CREATEDB PASSWORD 'app';

SELECT 'CREATE DATABASE authservice'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'authservice')
\gexec

SELECT 'CREATE DATABASE core'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'core')
\gexec

SELECT 'CREATE DATABASE doc_task'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'doc_task')
\gexec

SELECT 'CREATE DATABASE app OWNER app'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'app')
\gexec

ALTER DATABASE app OWNER TO app;
GRANT ALL PRIVILEGES ON DATABASE app TO app;

