#!/bin/bash

pgrep supervisord > /dev/null
if [ $? -ne 1 ]; then echo "ERROR: Supervisord is already running"; exit 1; fi

mkdir -p "$PGROOT" && chown -R postgres:postgres "$PGROOT"
mkdir -p "$PGLOG" && chown -R postgres:postgres "$PGLOG"

## Ensure all logfiles exist, most appliances will have
## a foreign data wrapper pointing to these files
for i in $(seq 0 6); do touch "${PGLOG}/postgresql-$i.csv"; done

python3 /configure_spilo.py all
(
    sudo PATH="$PATH" -u postgres /patroni_wait.sh -t 3600 -- /postgres_backup.sh "$WALE_ENV_DIR" "$PGDATA"
) &
exec supervisord --configuration=/etc/supervisor/supervisord.conf --nodaemon
