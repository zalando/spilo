#!/bin/bash

cd /
tar -xpJf a.tar.xz
rm a.tar.xz

pgrep supervisord > /dev/null
if [ $? -ne 1 ]; then echo "ERROR: Supervisord is already running"; exit 1; fi

mkdir -p "$PGLOG" && chown -R postgres:postgres "$PGROOT"

## Ensure all logfiles exist, most appliances will have
## a foreign data wrapper pointing to these files
for i in $(seq 0 7); do touch "${PGLOG}/postgresql-$i.csv"; done
chown -R postgres:postgres "$PGLOG"

if python3 /configure_spilo.py all; then
    (
        sudo PATH="$PATH" -u postgres /patroni_wait.sh -t 3600 -- /postgres_backup.sh "$WALE_ENV_DIR" "$PGDATA" "$BACKUP_NUM_TO_RETAIN"
    ) &
fi

exec supervisord --configuration=/etc/supervisor/supervisord.conf --nodaemon
