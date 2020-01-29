#!/bin/sh

if [ -f /a.tar.xz ]; then
    echo "decompressing spilo image..."
    if tar xpJf /a.tar.xz -C / > /dev/null 2>&1; then
        rm /a.tar.xz
        ln -snf dash /bin/sh
    else
        echo "failed to decompress spilo image"
        exit 1
    fi
fi

if [ "x$1" = "xinit" ]; then
    exec /usr/bin/dumb-init -c --rewrite 1:0 -- /bin/sh /launch.sh
fi

mkdir -p "$PGLOG" "$RW_DIR/postgresql" "$RW_DIR/tmp"

## Ensure all logfiles exist, most appliances will have
## a foreign data wrapper pointing to these files
for i in $(seq 0 7); do
    if [ ! -f "${PGLOG}/postgresql-$i.csv" ]; then
        touch "${PGLOG}/postgresql-$i.csv"
    fi
done
chown -R postgres:postgres "$PGROOT" "$RW_DIR/postgresql"
chmod 01777 "$RW_DIR/tmp"

if [ "$DEMO" = "true" ]; then
    python3 /scripts/configure_spilo.py patroni patronictl pgqd certificate pam-oauth2
elif python3 /scripts/configure_spilo.py all; then
    su postgres -c "PATH=$PATH /scripts/patroni_wait.sh -t 3600 -- envdir $WALE_ENV_DIR /scripts/postgres_backup.sh $PGDATA $BACKUP_NUM_TO_RETAIN" &
fi

sv_stop() {
    sv -w 86400 stop patroni
    sv -w 86400 stop /etc/service/*
}

trap sv_stop TERM QUIT INT

/usr/bin/runsvdir -P /etc/service &

wait
