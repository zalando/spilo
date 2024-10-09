#!/bin/bash

# Log function to capture timestamped logs
function log {
    echo "$(date "+%Y-%m-%d %H:%M:%S.%3N") - $0 - $*"
}

# Check if the script is provided with the PGDATA argument
[[ -z $1 ]] && log "Error: PGDATA is missing!" && echo "Usage: $0 PGDATA" && exit 1
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

# Ensure DAYS_TO_RETAIN is set, either externally or from BACKUP_NUM_TO_RETAIN
if [[ -z $DAYS_TO_RETAIN ]]; then
    DAYS_TO_RETAIN=$BACKUP_NUM_TO_RETAIN
    log "DAYS_TO_RETAIN was not set. Using BACKUP_NUM_TO_RETAIN value: $DAYS_TO_RETAIN"
    
    # Make sure there are at least 2 days of base backups before creating a new one
    [[ "$DAYS_TO_RETAIN" -lt 2 ]] && DAYS_TO_RETAIN=2
    log "Ensuring DAYS_TO_RETAIN is at least 2. Current value: $DAYS_TO_RETAIN"
fi

# Decide whether to use wal-g or wal-e for backup based on USE_WALG_BACKUP flag
if [[ "$USE_WALG_BACKUP" == "true" ]]; then
    readonly WAL_E="wal-g"
    log "Using wal-g for backup."
    
    # Optionally set compression method for wal-g if provided
    [[ -z $WALG_BACKUP_COMPRESSION_METHOD ]] || export WALG_COMPRESSION_METHOD=$WALG_BACKUP_COMPRESSION_METHOD
    export PGHOST=/var/run/postgresql
else
    readonly WAL_E="wal-e"
    log "Using wal-e for backup."
    
    # Determine pool size based on CPU count, but cap it at 4 to avoid excessive parallelism
    POOL_SIZE=$(grep -c ^processor /proc/cpuinfo 2>/dev/null || echo 1)
    [ "$POOL_SIZE" -gt 4 ] && POOL_SIZE=4
    POOL_SIZE=(--pool-size "$POOL_SIZE")
    log "POOL_SIZE set to $POOL_SIZE"
fi

# Initialization
BEFORE=""  # Backup candidate for deletion
LEFT=0    # Counter for backups that will remain
NOW=$(date +%s -u)
readonly NOW

log "Listing existing backups..."
# Loop through the existing backups and check if they qualify for deletion
while read -r name last_modified rest; do
    last_modified=$(date +%s -ud "$last_modified")
    
    # If a backup's age exceeds DAYS_TO_RETAIN, consider it for deletion
    if [ $(((NOW-last_modified)/86400)) -ge $DAYS_TO_RETAIN ]; then
        log "Backup $name is old enough for deletion."
        if [ -z "$BEFORE" ] || [ "$last_modified" -gt "$BEFORE_TIME" ]; then
            BEFORE_TIME=$last_modified
            BEFORE=$name
        fi
    else
        # Otherwise, increment the counter for backups that will remain
        ((LEFT=LEFT+1))
    fi
done < <($WAL_E backup-list 2> /dev/null | sed '0,/^name\s*\(last_\)\?modified\s*/d')

log "Total backups to retain: $LEFT. Target for deletion is: $BEFORE"

# Ensure a certain number of backups remain, even if their age exceeds DAYS_TO_RETAIN
if [ -n "$BEFORE" ] && [ $LEFT -ge $BACKUP_NUM_TO_RETAIN ]; then
    log "Deleting backups before $BEFORE..."
    # Use appropriate deletion command based on whether wal-g or wal-e is being used
    if [[ "$USE_WALG_BACKUP" == "true" ]]; then
        $WAL_E delete retain $LEFT --confirm
    else
        $WAL_E delete --confirm before "$BEFORE"
    fi
else
    log "No backups were deleted."
fi

# Push a new base backup with reduced CPU priority
log "Producing a new backup..."
exec nice -n 5 $WAL_E backup-push "$PGDATA" "${POOL_SIZE[@]}"
