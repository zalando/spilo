#!/bin/bash

function log
{
    echo "$(date "+%Y-%m-%d %H:%M:%S.%3N") - $0 - $*"
}

[[ -z $1 ]] && echo "Usage: $0 PGDATA" && exit 1

log "I was called as: $0 $*"


readonly PGDATA=$1

IN_RECOVERY=$(psql -tXqAc "select pg_catalog.pg_is_in_recovery()")
readonly IN_RECOVERY
if [[ $IN_RECOVERY == "f" ]]; then
    [[ "$WALG_BACKUP_FROM_REPLICA" == "true" ]] && log "Cluster is not in recovery, not running backup" && exit 0
elif [[ $IN_RECOVERY == "t" ]]; then
    [[ "$WALG_BACKUP_FROM_REPLICA" != "true" ]] && log "Cluster is in recovery, not running backup" && exit 0
else
    log "ERROR: Recovery state unknown: $IN_RECOVERY" && exit 1
fi

if [[ "$USE_WALG_BACKUP" == "true" ]]; then
    readonly WAL_E="wal-g"
    [[ -z $WALG_BACKUP_COMPRESSION_METHOD ]] || export WALG_COMPRESSION_METHOD=$WALG_BACKUP_COMPRESSION_METHOD
    export PGHOST=/var/run/postgresql
else
    readonly WAL_E="wal-e"

    # Ensure we don't have more workes than CPU's
    POOL_SIZE=$(grep -c ^processor /proc/cpuinfo 2>/dev/null || 1)
    [ "$POOL_SIZE" -gt 4 ] && POOL_SIZE=4
    POOL_SIZE=(--pool-size "$POOL_SIZE")
fi

# push a new base backup
log "producing a new backup"
# We reduce the priority of the backup for CPU consumption
nice -n 5 $WAL_E backup-push "$PGDATA" "${POOL_SIZE[@]}"

# Collect all backups and sort them by modification time
mapfile -t backup_records < <(wal-g backup-list 2>/dev/null |
    sed '0,/^\(backup_\)\?name\s*\(last_\)\?modified\s*/d' |
    awk '{ cmd = "date +%s -ud \"" $2 "\""; cmd | getline epoch; close(cmd); print epoch, $1 }' |
    sort -rn |
    awk '{ print $2 }'
    )

# Compute total after collection
TOTAL=${#backup_records[@]}

# leave at least 2 days base backups
[[ "$BACKUP_NUM_TO_RETAIN" -lt 2 ]] && BACKUP_NUM_TO_RETAIN=2

# get the date of the BACKUP_NUM_TO_RETAIN-th newest backup
if [[ $TOTAL -gt $BACKUP_NUM_TO_RETAIN ]]; then
    # check the current tool used for backups
    BEFORE="${backup_records[$BACKUP_NUM_TO_RETAIN-1]}"
    wal-g delete before FIND_FULL "$BEFORE" --confirm
else
    log "There are only $TOTAL backups, not deleting any"
fi
