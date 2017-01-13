#!/bin/bash

RETRIES=3

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

DATA_DIR=$(realpath $DATA_DIR)
XLOG_DIR=$(dirname $DATA_DIR)/xlog_fast

ATTEMPT=0
EXITCODE=1
while [[ $((ATTEMPT++)) < $RETRIES || $EXITCODE == 0 ]]; do
    pg_basebackup -P --pgdata="${DATA_DIR}" --xlog-method=stream --xlogdir="${XLOG_DIR}" --dbname="${CONNSTR}"
    EXITCODE=$?
done
exit $EXITCODE
