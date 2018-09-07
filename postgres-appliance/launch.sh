#!/bin/sh

if [ -f /a.tar.xz ]; then
    echo "decompressing spilo image..."
    cd /
    tar -xpJf a.tar.xz
    rm a.tar.xz
    ln -snf dash /bin/sh
fi

if [ "$DEMO" != "true" ]; then
    pgrep supervisord > /dev/null && echo "ERROR: Supervisord is already running" && exit 1
fi

mkdir -p "$PGLOG"

## Ensure all logfiles exist, most appliances will have
## a foreign data wrapper pointing to these files
for i in $(seq 0 7); do
    if [ ! -f "${PGLOG}/postgresql-$i.csv" ]; then
        touch "${PGLOG}/postgresql-$i.csv"
    fi
done
chown -R postgres:postgres "$PGROOT"

if [ "$DEMO" = "true" ]; then
    sed -i '/motd/d' /root/.bashrc
    python3 /scripts/configure_spilo.py patroni patronictl certificate pam-oauth2
    (
        su postgres -c 'env -i PGAPPNAME="pgq ticker" /scripts/patroni_wait.sh --role master -- /usr/bin/pgqd /home/postgres/pgq_ticker.ini'
    ) &
    exec su postgres -c "PATH=$PATH exec patroni /home/postgres/postgres.yml"
else
    if python3 /scripts/configure_spilo.py all; then
        (
            su postgres -c "PATH=$PATH /scripts/patroni_wait.sh -t 3600 -- envdir $WALE_ENV_DIR /scripts/postgres_backup.sh $PGDATA $BACKUP_NUM_TO_RETAIN"
        ) &
    fi
    exec supervisord --configuration=/etc/supervisor/supervisord.conf --nodaemon
fi
