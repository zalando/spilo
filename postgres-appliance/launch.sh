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

sysctl -w vm.dirty_background_bytes=67108864 > /dev/null 2>&1
sysctl -w vm.dirty_bytes=134217728 > /dev/null 2>&1

mkdir -p "$PGLOG" "$RW_DIR/postgresql" "$RW_DIR/tmp" "$RW_DIR/certs"
if [ "$(id -u)" -ne 0 ]; then
    sed -e "s/^postgres:x:[^:]*:[^:]*:/postgres:x:$(id -u):$(id -g):/" /etc/passwd > "$RW_DIR/tmp/passwd"
    cat "$RW_DIR/tmp/passwd" > /etc/passwd
    rm "$RW_DIR/tmp/passwd"
fi

## Ensure all logfiles exist, most appliances will have
## a foreign data wrapper pointing to these files
for i in $(seq 0 7); do
    if [ ! -f "${PGLOG}/postgresql-$i.csv" ]; then
        touch "${PGLOG}/postgresql-$i.csv"
    fi
done
chown -R postgres: "$PGROOT" "$RW_DIR/certs"
chmod -R go-w "$PGROOT"
chmod 01777 "$RW_DIR/tmp"

if [ "$DEMO" = "true" ]; then
    python3 /scripts/configure_spilo.py patroni pgqd certificate pam-oauth2
elif python3 /scripts/configure_spilo.py all; then
    CMD="/scripts/patroni_wait.sh -t 3600 -- envdir $WALE_ENV_DIR /scripts/postgres_backup.sh $PGDATA"
    if [ "$(id -u)" -ne 0 ]; then
        su postgres -c "PATH=$PATH $CMD" &
    else
        $CMD &
    fi
fi

sv_stop() {
    sv -w 86400 stop patroni
    sv -w 86400 stop /etc/service/*
}

trap sv_stop TERM QUIT INT

/usr/bin/runsvdir -P /etc/service &

wait
