#!/bin/bash

(echo "CREATE ROLE admin CREATEDB NOLOGIN;
CREATE ROLE $1;
CREATE ROLE robot_zmon;

CREATE EXTENSION pg_cron;

ALTER POLICY cron_job_policy ON cron.job USING (username = current_user OR
    (pg_has_role(current_user, 'admin', 'MEMBER')
    AND pg_has_role(username, 'admin', 'MEMBER')
    AND NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname = username AND rolsuper)
    ));
REVOKE SELECT ON cron.job FROM public;
GRANT SELECT ON cron.job TO admin;
GRANT UPDATE (database, nodename) ON cron.job TO admin;

CREATE OR REPLACE FUNCTION cron.schedule(p_schedule text, p_database text, p_command text)
RETURNS bigint
LANGUAGE plpgsql
AS \$function\$
DECLARE
    l_jobid bigint;
BEGIN
    IF NOT (SELECT rolcanlogin FROM pg_roles WHERE rolname = current_user)
    THEN RAISE 'You cannot create a job using a role that cannot log in';
    END IF;

    SELECT schedule INTO l_jobid FROM cron.schedule(p_schedule, p_command);
    UPDATE cron.job SET database = p_database, nodename = '' WHERE jobid = l_jobid;
    RETURN l_jobid;
END;
\$function\$;
REVOKE EXECUTE ON FUNCTION cron.schedule(text, text) FROM public;
GRANT EXECUTE ON FUNCTION cron.schedule(text, text) TO admin;
REVOKE EXECUTE ON FUNCTION cron.schedule(text, text, text) FROM public;
GRANT EXECUTE ON FUNCTION cron.schedule(text, text, text) TO admin;
REVOKE EXECUTE ON FUNCTION cron.unschedule(bigint) FROM public;
GRANT EXECUTE ON FUNCTION cron.unschedule(bigint) TO admin;
GRANT USAGE ON SCHEMA cron TO admin;

CREATE EXTENSION file_fdw;
CREATE SERVER pglog FOREIGN DATA WRAPPER file_fdw;
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
GRANT SELECT ON postgres_log TO ADMIN;"

# Sunday could be 0 or 7 depending on the format, we just create both
for i in $(seq 0 7); do
    echo "CREATE FOREIGN TABLE postgres_log_$i () INHERITS (postgres_log) SERVER pglog
    OPTIONS (filename '../pg_log/postgresql-$i.csv', format 'csv', header 'false');
GRANT SELECT ON postgres_log_$i TO ADMIN;

CREATE OR REPLACE VIEW failed_authentication_$i WITH (security_barrier) AS
SELECT *
  FROM postgres_log_$i
 WHERE command_tag = 'authentication'
   AND error_severity = 'FATAL';
ALTER VIEW failed_authentication_$i OWNER TO postgres;
GRANT SELECT ON TABLE failed_authentication_$i TO robot_zmon;
"
done

cat /_zmon_schema.dump

sed "s/:HUMAN_ROLE/$1/" /create_user_functions.sql

echo "\c template1
CREATE EXTENSION pg_stat_statements;
CREATE EXTENSION set_user;
GRANT EXECUTE ON FUNCTION set_user(text) TO admin;"

sed "s/:HUMAN_ROLE/$1/" /create_user_functions.sql) | psql -d $2
