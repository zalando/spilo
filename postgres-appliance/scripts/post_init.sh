#!/bin/bash

cd "$(dirname "${BASH_SOURCE[0]}")" || exit 1

PGVER=$(psql -d "$2" -XtAc "SELECT pg_catalog.current_setting('server_version_num')::int/10000")
if [ "$PGVER" -ge 12 ]; then RESET_ARGS="oid, oid, bigint"; fi

(echo "DO \$\$
BEGIN
    PERFORM * FROM pg_catalog.pg_authid WHERE rolname = 'admin';
    IF FOUND THEN
        ALTER ROLE admin WITH CREATEDB NOLOGIN NOCREATEROLE NOSUPERUSER NOREPLICATION INHERIT;
    ELSE
        CREATE ROLE admin CREATEDB;
    END IF;
END;\$\$;

DO \$\$
BEGIN
    PERFORM * FROM pg_catalog.pg_authid WHERE rolname = '$1';
    IF FOUND THEN
        ALTER ROLE $1 WITH NOCREATEDB NOLOGIN NOCREATEROLE NOSUPERUSER NOREPLICATION INHERIT;
    ELSE
        CREATE ROLE $1;
    END IF;
END;\$\$;

DO \$\$
BEGIN
    PERFORM * FROM pg_catalog.pg_authid WHERE rolname = 'robot_zmon';
    IF FOUND THEN
        ALTER ROLE robot_zmon WITH NOCREATEDB NOLOGIN NOCREATEROLE NOSUPERUSER NOREPLICATION INHERIT;
    ELSE
        CREATE ROLE robot_zmon;
    END IF;
END;\$\$;

CREATE EXTENSION IF NOT EXISTS pg_auth_mon SCHEMA public;
ALTER EXTENSION pg_auth_mon UPDATE;
GRANT SELECT ON TABLE public.pg_auth_mon TO robot_zmon;

CREATE EXTENSION IF NOT EXISTS pg_cron SCHEMA public;
ALTER EXTENSION pg_cron UPDATE;

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

CREATE EXTENSION IF NOT EXISTS file_fdw SCHEMA public;
DO \$\$
BEGIN
    PERFORM * FROM pg_catalog.pg_foreign_server WHERE srvname = 'pglog';
    IF NOT FOUND THEN
        CREATE SERVER pglog FOREIGN DATA WRAPPER file_fdw;
    END IF;
END;\$\$;

CREATE TABLE IF NOT EXISTS public.postgres_log (
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
GRANT SELECT ON public.postgres_log TO admin;"
if [ "$PGVER" -ge 13 ]; then
    echo "ALTER TABLE public.postgres_log ADD COLUMN IF NOT EXISTS backend_type text;"
fi

# Sunday could be 0 or 7 depending on the format, we just create both
for i in $(seq 0 7); do
    echo "CREATE FOREIGN TABLE IF NOT EXISTS public.postgres_log_$i () INHERITS (public.postgres_log) SERVER pglog
    OPTIONS (filename '../pg_log/postgresql-$i.csv', format 'csv', header 'false');
GRANT SELECT ON public.postgres_log_$i TO admin;

CREATE OR REPLACE VIEW public.failed_authentication_$i WITH (security_barrier) AS
SELECT *
  FROM public.postgres_log_$i
 WHERE command_tag = 'authentication'
   AND error_severity = 'FATAL';
ALTER VIEW public.failed_authentication_$i OWNER TO postgres;
GRANT SELECT ON TABLE public.failed_authentication_$i TO robot_zmon;
"
done

cat _zmon_schema.dump

while IFS= read -r db_name; do
    echo "\c ${db_name}"
    # In case if timescaledb binary is missing the first query fails with the error
    # ERROR:  could not access file "$libdir/timescaledb-$OLD_VERSION": No such file or directory
    TIMESCALEDB_VERSION=$(echo -e "SELECT NULL;\nSELECT extversion FROM pg_catalog.pg_extension WHERE extname = 'timescaledb'" | psql -tAX -d "${db_name}" 2> /dev/null | tail -n 1)
    if [ "x$TIMESCALEDB_VERSION" != "x" ] && [ "x$TIMESCALEDB_VERSION" != "x$TIMESCALEDB" ] \
            && { [ "$PGVER" -ge 11 ] || [ "x$TIMESCALEDB_VERSION" != "x$TIMESCALEDB_LEGACY" ]; }; then
        echo "ALTER EXTENSION timescaledb UPDATE;"
    fi
    UPGRADE_POSTGIS=$(echo -e "SELECT COUNT(*) FROM pg_catalog.pg_extension WHERE extname = 'postgis'" | psql -tAX -d "${db_name}" 2> /dev/null | tail -n 1)
    if [ "x$UPGRADE_POSTGIS" = "x1" ]; then
        # public.postgis_lib_version() is available only if postgis extension is created
        UPGRADE_POSTGIS=$(echo -e "SELECT extversion != public.postgis_lib_version() FROM pg_catalog.pg_extension WHERE extname = 'postgis'" | psql -tAX -d "${db_name}" 2> /dev/null | tail -n 1)
        if [ "x$UPGRADE_POSTGIS" = "xt" ]; then
            echo "ALTER EXTENSION postgis UPDATE;"
            echo "SELECT public.postgis_extensions_upgrade();"
        fi
    fi
    sed "s/:HUMAN_ROLE/$1/" create_user_functions.sql
    echo "CREATE EXTENSION IF NOT EXISTS pg_stat_statements SCHEMA public;
CREATE EXTENSION IF NOT EXISTS pg_stat_kcache SCHEMA public;
CREATE EXTENSION IF NOT EXISTS set_user SCHEMA public;
ALTER EXTENSION set_user UPDATE;
GRANT EXECUTE ON FUNCTION public.set_user(text) TO admin;
GRANT EXECUTE ON FUNCTION public.pg_stat_statements_reset($RESET_ARGS) TO admin;"
    if [ "x$ENABLE_PG_MON" = "xtrue" ] && [ "$PGVER" -ge 11 ]; then echo "CREATE EXTENSION IF NOT EXISTS pg_mon SCHEMA public;"; fi
    cat metric_helpers.sql
done < <(psql -d "$2" -tAc 'select pg_catalog.quote_ident(datname) from pg_catalog.pg_database where datallowconn')
) | PGOPTIONS="-c synchronous_commit=local" psql -Xd "$2"
