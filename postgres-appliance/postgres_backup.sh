#!/bin/bash

function log
{
    echo "$(date "+%Y-%m-%d %H:%M:%S.%3N") - $0 - $@"
}

[[ -z $2 ]] && echo "Usage: $0 WALE_ENV_DIR PGDATA" && exit 1

log "I was called as: $0 $@"

TIMEOUT=0
if [[ ! -z ${INITIAL_BACKUP+1} ]]
then
    log "Initial backup, we wait for the cluster to become available"
    TIMEOUT=3600
fi

WALE_ENV_DIR=$1
shift

PGDATA=$1
shift

/patroni_wait.sh master 60 $TIMEOUT
[ $? -ne 0 ] && log "PostgreSQL master is unavailable after $TIMEOUT seconds" && exit 0

# leave only 2 base backups before creating a new one
envdir "${WALE_ENV_DIR}" wal-e --aws-instance-profile delete --confirm retain 2

# push a new base backup
log "producing a new backup"
exec envdir "${WALE_ENV_DIR}" wal-e --aws-instance-profile backup-push "${PGDATA}"
