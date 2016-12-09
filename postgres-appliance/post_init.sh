#!/bin/bash

CONNSTRING=$1
psql -d $CONNSTRING <<EOF
CREATE EXTENSION file_fdw;
CREATE SERVER pglog FOREIGN DATA WRAPPER file_fdw;
CREATE ROLE admin CREATEROLE CREATEDB NOLOGIN;

CREATE TABLE postgres_log (
    log_time timestamp(3) with time zone,
    user_name text,
    database_name text,
    process_id integer,
    connection_from text,
    session_id text NOT NULL,
    session_line_num bigint NOT NULL,
    command_tag text,
    session_start_time timestamp with time zone,
    virtual_transaction_id text,
    transaction_id bigint,
    error_severity text,
    sql_state_code text,
    message text,
    detail text,
    hint text,
    internal_query text,
    internal_query_pos integer,
    context text,
    query text,
    query_pos integer,
    location text,
    application_name text,
    CONSTRAINT postgres_log_check CHECK (false) NO INHERIT
);

-- Sunday could be 0 or 7 depending on the format, we just create both
CREATE FOREIGN TABLE postgres_log_0 () INHERITS (postgres_log) SERVER pglog
    OPTIONS (filename '../pg_log/postgresql-0.csv', format 'csv', header 'false');
CREATE FOREIGN TABLE postgres_log_7 () INHERITS (postgres_log) SERVER pglog
    OPTIONS (filename '../pg_log/postgresql-7.csv', format 'csv', header 'false');

CREATE FOREIGN TABLE postgres_log_1 () INHERITS (postgres_log) SERVER pglog
    OPTIONS (filename '../pg_log/postgresql-1.csv', format 'csv', header 'false');
CREATE FOREIGN TABLE postgres_log_2 () INHERITS (postgres_log) SERVER pglog
    OPTIONS (filename '../pg_log/postgresql-2.csv', format 'csv', header 'false');
CREATE FOREIGN TABLE postgres_log_3 () INHERITS (postgres_log) SERVER pglog
    OPTIONS (filename '../pg_log/postgresql-3.csv', format 'csv', header 'false');
CREATE FOREIGN TABLE postgres_log_4 () INHERITS (postgres_log) SERVER pglog
    OPTIONS (filename '../pg_log/postgresql-4.csv', format 'csv', header 'false');
CREATE FOREIGN TABLE postgres_log_5 () INHERITS (postgres_log) SERVER pglog
    OPTIONS (filename '../pg_log/postgresql-5.csv', format 'csv', header 'false');
CREATE FOREIGN TABLE postgres_log_6 () INHERITS (postgres_log) SERVER pglog
    OPTIONS (filename '../pg_log/postgresql-6.csv', format 'csv', header 'false');
GRANT SELECT ON postgres_log TO ADMIN;
\c template1
CREATE EXTENSION hstore;
CREATE EXTENSION intarray;
CREATE EXTENSION ltree;
CREATE EXTENSION pgcrypto;
CREATE EXTENSION pg_stat_statements;
CREATE EXTENSION pgq;
CREATE EXTENSION pg_trgm;
CREATE EXTENSION plpgsql;
CREATE EXTENSION postgres_fdw;
EOF
