#!/bin/bash

set -euo pipefail

readonly databases=(post_init_test post-init-test PostInitTest 'post init test' 'post"init_test')
created_databases=()

function cleanup() {
    local database
    for database in "${created_databases[@]}"; do
        psql -Xv ON_ERROR_STOP=1 -d postgres -v database="$database" <<'SQL'
DROP DATABASE IF EXISTS :"database";
SQL
    done
}

# Use PostGIS's ANY helper path to exercise its upgrade SQL with one package.
trap cleanup EXIT
for database in "${databases[@]}"; do
    psql -Xv ON_ERROR_STOP=1 -d postgres -v database="$database" <<'SQL'
CREATE DATABASE :"database";
SQL
    created_databases+=("$database")
    psql -Xv ON_ERROR_STOP=1 -d "$database" <<'SQL'
CREATE EXTENSION postgis;
ALTER EXTENSION postgis UPDATE TO "ANY";
SQL
done

/scripts/post_init.sh "${HUMAN_ROLE:-zalandos}" postgres

for database in "${databases[@]}"; do
    psql -Xv ON_ERROR_STOP=1 -d "$database" <<'SQL'
DO $$
BEGIN
    IF (SELECT extversion FROM pg_extension WHERE extname = 'postgis')
       IS DISTINCT FROM public.postgis_lib_version() THEN
        RAISE EXCEPTION 'PostGIS was not upgraded in database %', current_database();
    END IF;
END
$$;
SELECT current_database() AS database, extversion AS postgis_version
  FROM pg_extension WHERE extname = 'postgis';
SQL
done
