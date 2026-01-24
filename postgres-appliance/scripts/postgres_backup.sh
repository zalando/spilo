#!/bin/bash

set -o pipefail

function log
{
    echo "$(date "+%Y-%m-%d %H:%M:%S.%3N") - $0 - $*"
}

[[ -z $1 ]] && echo "Usage: $0 PGDATA" && exit 1

log "I was called as: $0 $*"

readonly PGDATA=$1
BACKUP_NUM_TO_RETAIN=${BACKUP_NUM_TO_RETAIN:-2}
DAYS_TO_RETAIN=${DAYS_TO_RETAIN:-$BACKUP_NUM_TO_RETAIN}

IN_RECOVERY=$(psql -tXqAc "select pg_catalog.pg_is_in_recovery()")
readonly IN_RECOVERY
if [[ $IN_RECOVERY == "f" ]]; then
    [[ "$WALG_BACKUP_FROM_REPLICA" == "true" ]] && log "Cluster is not in recovery, not running backup" && exit 0
elif [[ $IN_RECOVERY == "t" ]]; then
    [[ "$WALG_BACKUP_FROM_REPLICA" != "true" ]] && log "Cluster is in recovery, not running backup" && exit 0
else
    log "ERROR: Recovery state unknown: $IN_RECOVERY" && exit 1
fi

export WALG_COMPRESSION_METHOD="${WALG_BACKUP_COMPRESSION_METHOD:-${WALE_BACKUP_COMPRESSION_METHOD:-$WALG_COMPRESSION_METHOD}}"
export PGHOST=/run/postgresql

# Exponential backoff config
BASE_DELAY=900       # Starting delay: 15 minutes
MAX_RETRIES=3        # Total number of retries (excluding initial attempt)

# Loop for initial attempt + retries
for ((i=0; i<=MAX_RETRIES; i++)); do
    log "Producing a new backup (Attempt $((i+1)) of $((MAX_RETRIES+1)))..."

    # Run the backup command
    nice -n 5 wal-g backup-push "$PGDATA"
    EXIT_CODE=$?
    if [ $EXIT_CODE -eq 0 ]; then
        log "Backup successful on attempt $((i+1))."
        break
    else
        log "Backup failed with exit code $EXIT_CODE."

        # If we have used up all retries, fail the script
        if [[ $i -eq $MAX_RETRIES ]]; then
            log "ERROR: All backup attempts failed. Exiting."
            exit $EXIT_CODE
        fi

        # Calculate exponential wait: BASE_DELAY * (2^i)
        WAIT_TIME=$(( BASE_DELAY * (2**i) ))
        log "Retrying in $((WAIT_TIME/60)) minutes..."
        sleep "$WAIT_TIME"
    fi
done

# leave at least 2 days base backups and/or 2 backups
[[ "$BACKUP_NUM_TO_RETAIN" -lt 2 ]] && BACKUP_NUM_TO_RETAIN=2
[[ "$DAYS_TO_RETAIN" -lt 2 ]] && DAYS_TO_RETAIN=2

unset WALG_LOG_LEVEL
unset S3_LOG_LEVEL

TARGET_BACKUP=$(wal-g backup-list --json 2>/dev/null | jq -r \
    --argjson min_count "$BACKUP_NUM_TO_RETAIN" \
    --argjson days "$DAYS_TO_RETAIN" \
    'sort_by(.time) | reverse
    | .[$min_count - 1:]
    | map(select((now - (.time | sub("\\.[0-9]+Z$"; "Z") | fromdateiso8601)) >= ($days * 86400)))
    | first
    | .backup_name // ""')

if [[ -z "$TARGET_BACKUP" ]]; then
    log "No backups older than $DAYS_TO_RETAIN days found, not deleting any"
    exit 0
fi

if [[ -n "$TARGET_BACKUP" ]]; then
    log "Found target boundary backup: $TARGET_BACKUP"
    wal-g delete before FIND_FULL "$TARGET_BACKUP" --confirm
else
    log "No backups found eligible for deletion."
fi
