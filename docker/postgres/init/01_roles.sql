\set ON_ERROR_STOP 1

\getenv macrodb_owner_url MACRODB_OWNER_URL
\getenv macrodb_app_url MACRODB_APP_URL

SELECT regexp_replace(
    :'macrodb_owner_url',
    '^[^:]+://[^:]+:([^@]+)@.*$',
    '\1'
) AS macrodb_owner_password \gset

SELECT regexp_replace(
    :'macrodb_app_url',
    '^[^:]+://[^:]+:([^@]+)@.*$',
    '\1'
) AS macrodb_app_password \gset

SELECT 'CREATE ROLE macrodb_owner LOGIN PASSWORD ' || quote_literal(:'macrodb_owner_password')
WHERE NOT EXISTS (
    SELECT 1
    FROM pg_roles
    WHERE rolname = 'macrodb_owner'
) \gexec

ALTER ROLE macrodb_owner WITH LOGIN PASSWORD :'macrodb_owner_password';

SELECT 'CREATE ROLE macrodb_app LOGIN PASSWORD ' || quote_literal(:'macrodb_app_password')
WHERE NOT EXISTS (
    SELECT 1
    FROM pg_roles
    WHERE rolname = 'macrodb_app'
) \gexec

ALTER ROLE macrodb_app WITH LOGIN PASSWORD :'macrodb_app_password';

SELECT 'CREATE DATABASE macrodb_dev OWNER macrodb_owner'
WHERE NOT EXISTS (
    SELECT 1
    FROM pg_database
    WHERE datname = 'macrodb_dev'
) \gexec

SELECT 'CREATE DATABASE macrodb_test OWNER macrodb_owner'
WHERE NOT EXISTS (
    SELECT 1
    FROM pg_database
    WHERE datname = 'macrodb_test'
) \gexec

ALTER DATABASE macrodb_dev OWNER TO macrodb_owner;
ALTER DATABASE macrodb_test OWNER TO macrodb_owner;

GRANT CONNECT ON DATABASE macrodb_dev TO macrodb_app;
GRANT CONNECT ON DATABASE macrodb_test TO macrodb_app;

\connect macrodb_dev

CREATE EXTENSION IF NOT EXISTS vector;

GRANT USAGE ON SCHEMA public TO macrodb_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO macrodb_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO macrodb_app;

ALTER DEFAULT PRIVILEGES FOR ROLE macrodb_owner IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO macrodb_app;

ALTER DEFAULT PRIVILEGES FOR ROLE macrodb_owner IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO macrodb_app;

\connect macrodb_test

CREATE EXTENSION IF NOT EXISTS vector;

GRANT USAGE ON SCHEMA public TO macrodb_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO macrodb_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO macrodb_app;

ALTER DEFAULT PRIVILEGES FOR ROLE macrodb_owner IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO macrodb_app;

ALTER DEFAULT PRIVILEGES FOR ROLE macrodb_owner IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO macrodb_app;
