#!/bin/bash

cd "$(dirname "${BASH_SOURCE[0]}")" || exit 1

export PGOPTIONS="-c synchronous_commit=local -c search_path=pg_catalog"

PGVER=$(psql -d "$2" -XtAc "SELECT pg_catalog.current_setting('server_version_num')::int/10000")
RESET_ARGS="oid, oid, bigint"

(echo "\set ON_ERROR_STOP on"
echo "DO \$\$
BEGIN
    PERFORM * FROM pg_catalog.pg_authid WHERE rolname = 'admin';
    IF FOUND THEN
        ALTER ROLE admin WITH CREATEDB NOLOGIN NOCREATEROLE NOSUPERUSER NOREPLICATION INHERIT;
    ELSE
        CREATE ROLE admin CREATEDB;
    END IF;

    PERFORM * FROM pg_catalog.pg_authid WHERE rolname = 'cron_admin';
    IF FOUND THEN
        ALTER ROLE cron_admin WITH NOCREATEDB NOLOGIN NOCREATEROLE NOSUPERUSER NOREPLICATION INHERIT;
    ELSE
        CREATE ROLE cron_admin;
    END IF;
END;\$\$;

GRANT cron_admin TO admin;

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

CREATE EXTENSION IF NOT EXISTS pg_cron SCHEMA pg_catalog;
DO \$\$
BEGIN
    PERFORM 1 FROM pg_catalog.pg_proc WHERE pronamespace = 'cron'::pg_catalog.regnamespace AND proname = 'schedule' AND proargnames = '{p_schedule,p_database,p_command}';
    IF FOUND THEN
        ALTER FUNCTION cron.schedule(text, text, text) RENAME TO schedule_in_database;
    END IF;
END;\$\$;
ALTER EXTENSION pg_cron UPDATE;

ALTER POLICY cron_job_policy ON cron.job USING (username = current_user OR
    (pg_has_role(current_user, 'cron_admin', 'MEMBER')
    AND pg_has_role(username, 'cron_admin', 'MEMBER')
    AND NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname = username AND rolsuper)
    ));
REVOKE SELECT ON cron.job FROM admin, public;
GRANT SELECT ON cron.job TO cron_admin;
REVOKE UPDATE (database, nodename) ON cron.job FROM admin;
GRANT UPDATE (database, nodename) ON cron.job TO cron_admin;

ALTER POLICY cron_job_run_details_policy ON cron.job_run_details USING (username = current_user OR
    (pg_has_role(current_user, 'cron_admin', 'MEMBER')
    AND pg_has_role(username, 'cron_admin', 'MEMBER')
    AND NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname = username AND rolsuper)
    ));
REVOKE SELECT ON cron.job_run_details FROM admin, public;
GRANT SELECT ON cron.job_run_details TO cron_admin;

CREATE OR REPLACE FUNCTION cron.schedule_in_database(p_schedule text, p_database text, p_command text)
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

REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA cron FROM admin, public;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA cron TO cron_admin;

REVOKE USAGE ON SCHEMA cron FROM admin;
GRANT USAGE ON SCHEMA cron TO cron_admin;

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
if [ "$PGVER" -ge 14 ]; then
    echo "ALTER TABLE public.postgres_log ADD COLUMN IF NOT EXISTS leader_pid integer;"
    echo "ALTER TABLE public.postgres_log ADD COLUMN IF NOT EXISTS query_id bigint;"
fi

# Sunday could be 0 or 7 depending on the format, we just create both
LOG_SHIP_HOURLY=$(echo "SELECT text(current_setting('log_rotation_age') = '1h')" | psql -tAX -d postgres 2> /dev/null | tail -n 1)
if [ "$LOG_SHIP_HOURLY" != "true" ]; then
    tbl_regex='postgres_log_\d_\d{2}$'
else
    tbl_regex='postgres_log_\d$'
fi
echo "DO \$\$DECLARE tbl_name TEXT;
    BEGIN
    FOR tbl_name IN SELECT 'public' || '.' || quote_ident(relname) FROM pg_class
                    WHERE relname ~ '${tbl_regex}' AND relnamespace = 'public'::pg_catalog.regnamespace AND relkind = 'f'
    LOOP
        IF tbl_name IS NOT NULL THEN
            EXECUTE format('DROP FOREIGN TABLE IF EXISTS %s CASCADE', tbl_name);
        END IF;
    END LOOP;
END;\$\$;"

for i in $(seq 0 7); do
    if [ "$LOG_SHIP_HOURLY" != "true" ]; then
        echo "CREATE FOREIGN TABLE IF NOT EXISTS public.postgres_log_${i} () INHERITS (public.postgres_log) SERVER pglog
        OPTIONS (filename '../pg_log/postgresql-${i}.csv', format 'csv', header 'false');
        GRANT SELECT ON public.postgres_log_${i} TO admin;

        CREATE OR REPLACE VIEW public.failed_authentication_${i} WITH (security_barrier) AS
        SELECT *
          FROM public.postgres_log_${i}
         WHERE command_tag = 'authentication'
           AND error_severity = 'FATAL';
        ALTER VIEW public.failed_authentication_${i} OWNER TO postgres;
        GRANT SELECT ON TABLE public.failed_authentication_${i} TO robot_zmon;"
    else
        daily_log="CREATE OR REPLACE VIEW public.postgres_log_${i} AS\n"
        daily_auth="CREATE OR REPLACE VIEW public.failed_authentication_${i} WITH (security_barrier) AS\n"
        daily_union=""

        for h in $(seq -w 0 23); do
            filter_logs="SELECT * FROM public.postgres_log_${i}_${h} WHERE command_tag = 'authentication' AND error_severity = 'FATAL'"

            echo "CREATE FOREIGN TABLE IF NOT EXISTS public.postgres_log_${i}_${h} () INHERITS (public.postgres_log) SERVER pglog
            OPTIONS (filename '../pg_log/postgresql-${i}-${h}.csv', format 'csv', header 'false');
            GRANT SELECT ON public.postgres_log_${i}_${h} TO admin;

            CREATE OR REPLACE VIEW public.failed_authentication_${i}_${h} WITH (security_barrier) AS
            ${filter_logs};
            ALTER VIEW public.failed_authentication_${i}_${h} OWNER TO postgres;
            GRANT SELECT ON TABLE public.failed_authentication_${i}_${h} TO robot_zmon;"

            daily_log="${daily_log}${daily_union}SELECT * FROM public.postgres_log_${i}_${h}\n"
            daily_auth="${daily_auth}${daily_union}${filter_logs}\n"
            daily_union="UNION ALL\n"
        done

        echo -e "${daily_log};"
        echo -e "${daily_auth};"
    fi
done

cat _zmon_schema.dump

while IFS= read -r db_name; do
    echo "\c ${db_name}"
    # In case if timescaledb binary is missing the first query fails with the error
    # ERROR:  could not access file "$libdir/timescaledb-$OLD_VERSION": No such file or directory
    UPGRADE_TIMESCALEDB=$(echo -e "SELECT NULL;\nSELECT default_version != installed_version FROM pg_catalog.pg_available_extensions WHERE name = 'timescaledb'" | psql -tAX -d "${db_name}" 2> /dev/null | tail -n 1)
    if [ "$UPGRADE_TIMESCALEDB" = "t" ]; then
        echo "ALTER EXTENSION timescaledb UPDATE;"
    fi
    UPGRADE_TIMESCALEDB_TOOLKIT=$(echo -e "SELECT NULL;\nSELECT default_version != installed_version FROM pg_catalog.pg_available_extensions WHERE name = 'timescaledb_toolkit'" | psql -tAX -d "${db_name}" 2> /dev/null | tail -n 1)
    if [ "$UPGRADE_TIMESCALEDB_TOOLKIT" = "t" ]; then
        echo "ALTER EXTENSION timescaledb_toolkit UPDATE;"
    fi
    UPGRADE_POSTGIS=$(echo "SELECT COUNT(*) FROM pg_catalog.pg_extension WHERE extname = 'postgis'" | psql -tAX -d "${db_name}" 2> /dev/null | tail -n 1)
    if [ "$UPGRADE_POSTGIS" = "1" ]; then
        # public.postgis_lib_version() is available only if postgis extension is created
        UPGRADE_POSTGIS=$(echo "SELECT extversion != public.postgis_lib_version() FROM pg_catalog.pg_extension WHERE extname = 'postgis'" | psql -tAX -d "${db_name}" 2> /dev/null | tail -n 1)
        if [ "$UPGRADE_POSTGIS" = "t" ]; then
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
    echo "GRANT EXECUTE ON FUNCTION pg_catalog.pg_switch_wal() TO admin;"
    if [ "$ENABLE_PG_MON" = "true" ]; then echo "CREATE EXTENSION IF NOT EXISTS pg_mon SCHEMA public;"; fi
    cat metric_helpers.sql
done < <(psql -d "$2" -tAc 'select pg_catalog.quote_ident(datname) from pg_catalog.pg_database where datallowconn')
) | psql -Xd "$2"
