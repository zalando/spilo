#!/bin/bash

function log
{
    echo "$(date "+%Y-%m-%d %H:%M:%S.%3N") - $0 - $@"
}

[[ -z $2 ]] && echo "Usage: $0 WALE_ENV_DIR PGDATA" && exit 1

log "I was called as: $0 $@"


readonly WALE_ENV_DIR=$1
readonly PGDATA=$2
NUM_TO_RETAIN=$3

readonly IN_RECOVERY=$(psql -tXqAc "select pg_is_in_recovery()")
[[ $IN_RECOVERY != "f" ]] && log "Cluster is in recovery, not running backup" && exit 0

# leave at least 2 days base backups before creating a new one
[[ "$NUM_TO_RETAIN" -lt 2 ]] && NUM_TO_RETAIN=2

readonly WAL_E="envdir $WALE_ENV_DIR wal-e --aws-instance-profile"

BEFORE=""

readonly NOW=$(date +%s -u)
while read name last_modified rest; do
    last_modified=$(date +%s -ud "$last_modified")
    if [ $(((NOW-last_modified)/86400)) -gt $NUM_TO_RETAIN ]; then
        if [ -z "$BEFORE" ] || [ "$last_modified" -lt "$BEFORE_TIME" ]; then
            BEFORE_TIME=$last_modified
            BEFORE=$name
        fi
    fi
done < <($WAL_E backup-list 2> /dev/null | sed '0,/^name\s*last_modified\s*/d')

if [ ! -z "$BEFORE" ]; then
    $WAL_E delete --confirm before "$BEFORE"
fi

# Ensure we don't have more workes than CPU's
POOL_SIZE=$(grep -c ^processor /proc/cpuinfo 2>/dev/null || 1)
[ $POOL_SIZE -gt 4 ] && POOL_SIZE=4

# push a new base backup
log "producing a new backup"
# We reduce the priority of the backup for CPU consumption
exec nice -n 5 $WAL_E backup-push "${PGDATA}" --pool-size ${POOL_SIZE}
