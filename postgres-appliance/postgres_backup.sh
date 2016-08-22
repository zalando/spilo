#!/bin/bash

function log
{
    echo "$(date "+%Y-%m-%d %H:%M:%S.%3N") - $0 - $@"
}

[[ -z $2 ]] && echo "Usage: $0 WALE_ENV_DIR PGDATA" && exit 1

log "I was called as: $0 $@"


WALE_ENV_DIR=$1
shift

PGDATA=$1
shift

IN_RECOVERY=$(psql -tXqAc "select pg_is_in_recovery()")
[[ $IN_RECOVERY != "f" ]] && log "Cluster is in recovery, not running backup" && exit 0

# leave only 2 base backups before creating a new one
envdir "${WALE_ENV_DIR}" wal-e --aws-instance-profile delete --confirm retain 2

# Ensure we don't have more workes than CPU's
POOL_SIZE=4
[ $(nproc) -lt $POOL_SIZE ] && POOL_SIZE=$(nproc)

# push a new base backup
log "producing a new backup"
# We reduce the priority of the backup for CPU consumption
exec nice -n 5 envdir "${WALE_ENV_DIR}" wal-e --aws-instance-profile backup-push "${PGDATA}" --pool-size ${POOL_SIZE}
