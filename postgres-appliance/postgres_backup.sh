#!/bin/bash

function log
{
    echo "$(date "+%Y-%m-%d %H:%M:%S.%3N") - $0 - $@"
}

function wait_for_cluster
{
    local SECONDS=${1}
    [[ -z $1 ]] && SECONDS=0
    local FINAL_EPOCH=$(date --date "$SECONDS seconds" +%s)

    while true
    do
        pg_isready --quiet && return 0
        log "Cluster is not yet available, waiting"
        [[ $(date +%s) -lt ${FINAL_EPOCH} ]] || break
        sleep 5
    done

    log "ERROR: cluster was not available after $SECONDS seconds"
    return 1
}

[[ -z $2 ]] && echo "Usage: $0 WALE_ENV_DIR PGDATA" && exit 1

log "I was called as: $0 $@"

if [[ ! -z ${INITIAL_BACKUP+1} ]]
then
    log "Initial backup, we wait for the cluster to become available"
    wait_for_cluster 3600
fi

WALE_ENV_DIR=$1
shift

PGDATA=$1
shift



IN_RECOVERY=$(psql -tXqAc "select pg_is_in_recovery()")
[[ $IN_RECOVERY != "f" ]] && echo "Cluster is in recovery, not running backup" && exit 0

# leave only 2 base backups before creating a new one
envdir "${WALE_ENV_DIR}" wal-e --aws-instance-profile delete --confirm retain 2

# push a new base backup
log "producing a new backup"
envdir "${WALE_ENV_DIR}" wal-e --aws-instance-profile backup-push "${PGDATA}"
