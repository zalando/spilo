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

ATTEMPT=0
while [[ $((ATTEMPT++)) -le $RETRIES ]]; do
    rm -fr "${DATA_DIR}"
    pg_basebackup --pgdata="${DATA_DIR}" --xlog-method=stream --dbname="${CONNSTR}"
    EXITCODE=$?
    if [[ $EXITCODE == 0 ]]; then
        XLOG_FAST=$(dirname $DATA_DIR)/xlog_fast
        rm -fr $XLOG_FAST
        mv ${DATA_DIR}/pg_xlog $XLOG_FAST
        rm -fr $XLOG_FAST/archive_status
        mkdir ${DATA_DIR}/pg_xlog
        break
    elif [[ $ATTEMPT -le $RETRIES ]]; then
        sleep $((ATTEMPT*10))
    fi
done
exit $EXITCODE
