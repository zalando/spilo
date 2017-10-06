#!/bin/bash

PARSED=$(getopt --options v --longoptions connstring:,retries:,datadir: --name "$0" -- "$@" 2> /dev/null)
eval set -- "$PARSED"

RETRIES=2

while [[ $# -gt 0 ]]; do
    case $1 in
        --datadir )
            DATA_DIR=$2
            shift
            ;;
        --connstring )
            CONNSTR=$2
            shift
            ;;
        --retries )
            RETRIES=$2
            shift
            ;;
        * )
            ;;
    esac
    shift
done

[[ -z $DATA_DIR || -z $CONNSTR || ! $RETRIES =~ ^[1-9]$ ]] && exit 1

function receivewal() {
    pg_receivewal --directory="${WAL_FAST}" --dbname="${CONNSTR}" &
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
    pg_basebackup --pgdata="${DATA_DIR}" --wal-method=stream --dbname="${CONNSTR}"
    EXITCODE=$?
    if [[ $EXITCODE == 0 ]]; then
        WAL_FAST=$(dirname $DATA_DIR)/wal_fast
        WAL_DIR=${DATA_DIR}/pg_wal
        if [[ ! -d ${WAL_DIR} ]]; then
            WAL_DIR=${DATA_DIR}/pg_xlog
        fi
        rm -fr $WAL_FAST
        mv $WAL_DIR $WAL_FAST
        rm -fr $WAL_FAST/archive_status
        mkdir $WAL_DIR

        receivewal &
        break
    elif [[ $ATTEMPT -le $RETRIES ]]; then
        sleep $((ATTEMPT*10))
    fi
done
exit $EXITCODE
