#!/bin/bash

RETRIES=2

while getopts ":-:" optchar; do
    [[ "${optchar}" == "-" ]] || continue
    case "${OPTARG}" in
        datadir=* )
            DATA_DIR=${OPTARG#*=}
            ;;
        connstring=* )
            CONNSTR=${OPTARG#*=}
            ;;
        retries=* )
            RETRIES=${OPTARG#*=}
            ;;
    esac
done

[[ -z $DATA_DIR || -z $CONNSTR || ! $RETRIES =~ ^[1-9]$ ]] && exit 1

if which pg_receivewal &> /dev/null; then
    PG_RECEIVEWAL=pg_receivewal
    PG_BASEBACKUP_OPTS="-X none"
else
    PG_RECEIVEWAL=pg_receivexlog
    PG_BASEBACKUP_OPTS=""
fi

readonly WAL_FAST=$(dirname $DATA_DIR)/wal_fast
mkdir -p $WAL_FAST

# make sure that there is no receivewal running
exec 9>$WAL_FAST/receivewal.lock
if flock -x -n 9; then
    $PG_RECEIVEWAL --directory="${WAL_FAST}" --dbname="${CONNSTR}" &
    receivewal_pid=$!

    # run pg_receivewal until postgres will not start streaming
    (
        while ! ps ax | grep -qE '[w]al receiver process\s+streaming'; do
            # exit if pg_receivewal is not running
            kill -0 $receivewal_pid && sleep 1 || exit
        done

        kill $receivewal_pid && sleep 1
        rm -f ${WAL_FAST}/*
    )&
fi

ATTEMPT=0
while [[ $((ATTEMPT++)) -le $RETRIES ]]; do
    rm -fr "${DATA_DIR}"
    pg_basebackup --pgdata="${DATA_DIR}" ${PG_BASEBACKUP_OPTS} --dbname="${CONNSTR}"
    EXITCODE=$?
    if [[ $EXITCODE == 0 ]]; then
        break
    elif [[ $ATTEMPT -le $RETRIES ]]; then
        sleep $((ATTEMPT*10))
    fi
done

[[ $EXITCODE != 0 && ! -z $receivewal_pid ]] && kill $receivewal_pid
exit $EXITCODE
