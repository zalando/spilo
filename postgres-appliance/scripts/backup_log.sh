#!/bin/bash

function log
{
    echo "$(date "+%Y-%m-%d %H:%M:%S.%3N") - $0 - $@"
}

[[ -z $1 ]] && echo "Usage: $0 LOG_ENV_DIR" && exit 1

log "I was called as: $0 $@"

LOG_ENV_DIR=$1
shift

log "compressing and uploading to the cloud the postgres log"
exec nice -n 5 envdir "${LOG_ENV_DIR}" /scripts/upload_pg_log_to_s3.py
