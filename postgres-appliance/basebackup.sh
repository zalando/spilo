#!/bin/bash

PARSED=$(getopt --options v --longoptions connstring:,retries:,datadir: --name "$0" -- "$@" 2> /dev/null)
eval set -- "$PARSED"

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

function receivewal() {
    if which pg_receivewal &> /dev/null; then
        PG_RECEIVEWAL=pg_receivewal
    else
        PG_RECEIVEWAL=pg_receivexlog
    fi
    $PG_RECEIVEWAL --directory="${WAL_FAST}" --dbname="${CONNSTR}" &
    receivewal_pid=$!

    # run pg_receivewal until postgres will not start streaming
    while ! ps ax | grep -qE '[w]al receiver process\s+streaming'; do
        # exit if pg_receivewal is not running
        kill -0 $receivewal_pid && sleep 1 || exit
    done

    kill $receivewal_pid && sleep 1
    rm -f ${WAL_FAST}/*
}

ATTEMPT=0
while [[ $((ATTEMPT++)) -le $RETRIES ]]; do
    rm -fr "${DATA_DIR}"
    pg_basebackup --pgdata="${DATA_DIR}" -X stream --dbname="${CONNSTR}"
    EXITCODE=$?
    if [[ $EXITCODE == 0 ]]; then
        WAL_FAST=$(dirname $DATA_DIR)/wal_fast

        WAL_DIR=${DATA_DIR}/pg_wal
        [[ -d ${WAL_DIR} ]] || WAL_DIR=${DATA_DIR}/pg_xlog

        rm -fr $WAL_FAST $WAL_DIR/archive_status

        mv $WAL_DIR $WAL_FAST
        mkdir $WAL_DIR

        receivewal &
        break
    elif [[ $ATTEMPT -le $RETRIES ]]; then
        sleep $((ATTEMPT*10))
    fi
done
exit $EXITCODE
