#!/bin/bash

RETRIES=2
THRESHOLD_PERCENTAGE=30
THRESHOLD_MEGABYTES=10240

export PGOPTIONS="-c search_path=pg_catalog"

while getopts ":-:" optchar; do
    [[ "${optchar}" == "-" ]] || continue
    case "${OPTARG}" in
        datadir=* )
            DATA_DIR=${OPTARG#*=}
            ;;
        connstring=* )
            CONNSTR="${OPTARG#*=}"
            ;;
        retries=* )
            RETRIES=${OPTARG#*=}
            ;;
        threshold_backup_size_percentage=*|threshold-backup-size-percentage=* )
            THRESHOLD_PERCENTAGE=${OPTARG#*=}
            ;;
        threshold_megabytes=*|threshold-megabytes=* )
            THRESHOLD_MEGABYTES=${OPTARG#*=}
            ;;
        no_master=*|no-master=* )
            NO_MASTER=${OPTARG#*=}
            ;;
    esac
done

[[ -z $DATA_DIR ]] && exit 1
[[ -z $NO_MASTER && -z "$CONNSTR" ]] && exit 1

if [[ "$USE_WALG_RESTORE" == "true" ]]; then
    readonly WAL_E="wal-g"
else
    readonly WAL_E="wal-e"
fi

ATTEMPT=0
server_version="-1"
while true; do
    [[ -z $wal_segment_backup_start ]] && wal_segment_backup_start=$($WAL_E backup-list 2> /dev/null \
        | sed '0,/^(backup_\)?name\s*\(last_\)\?modified\s*/d' | sort -bk2 | tail -n1 | awk '{print $3;}' | sed 's/_.*$//')

    [[ -n "$CONNSTR" && $server_version == "-1" ]] && server_version=$(psql -d "$CONNSTR" -tAc 'show server_version_num' 2> /dev/null || echo "-1")

    [[ -n $wal_segment_backup_start && ( -z "$CONNSTR" || $server_version != "-1") ]] && break
    [[ $((ATTEMPT++)) -ge $RETRIES ]] && break
    sleep 1
done

[[ -z $wal_segment_backup_start ]] && echo "Can not find any backups" && exit 1

[[ -z $NO_MASTER && $server_version == "-1" ]] && echo "Failed to reach master" && exit 1

if [[ $server_version != "-1" ]]; then
    readonly lsn_segment=$((16#${wal_segment_backup_start:8:8}))
    readonly lsn_offset=$((16#${wal_segment_backup_start:16:8}))
    printf -v backup_start_lsn "%X/%X" $lsn_segment $((lsn_offset << 24))

    if [[ $server_version -ge 100000 ]]; then
        readonly query="SELECT CASE WHEN pg_is_in_recovery() THEN GREATEST(pg_wal_lsn_diff(COALESCE(pg_last_wal_receive_lsn(), '0/0'), '$backup_start_lsn')::bigint, pg_wal_lsn_diff(pg_last_wal_replay_lsn(), '$backup_start_lsn')::bigint) ELSE pg_wal_lsn_diff(pg_current_wal_lsn(), '$backup_start_lsn')::bigint END"
    else
        readonly query="SELECT CASE WHEN pg_is_in_recovery() THEN GREATEST(pg_xlog_location_diff(COALESCE(pg_last_xlog_receive_location(), '0/0'), '$backup_start_lsn')::bigint, pg_xlog_location_diff(pg_last_xlog_replay_location(), '$backup_start_lsn')::bigint) ELSE pg_xlog_location_diff(pg_current_xlog_location(), '$backup_start_lsn')::bigint END"
    fi

    ATTEMPT=0
    while true; do
        [[ -z $diff_in_bytes ]] && diff_in_bytes=$(psql -d "$CONNSTR" -tAc "$query")
        [[ -z $cluster_size ]] && cluster_size=$(psql -d "$CONNSTR" -tAc "SELECT SUM(pg_catalog.pg_database_size(datname)) FROM pg_catalog.pg_database")
        [[ -n $diff_in_bytes && -n $cluster_size ]] && break
        [[ $((ATTEMPT++)) -ge $RETRIES ]] && break
        sleep 1
    done
    [[ -z $diff_in_bytes || -z $cluster_size ]] && echo "could not determine difference with the master location" && exit 1

    echo "Current cluster size: $cluster_size"
    echo "Wals generated since the last backup: $diff_in_bytes"

    [[ $diff_in_bytes -gt $((THRESHOLD_MEGABYTES*1048576)) ]] && echo "not restoring from backup because of amount of generated wals exceeds ${THRESHOLD_MEGABYTES}MB" && exit 1

    readonly threshold_bytes=$((cluster_size*THRESHOLD_PERCENTAGE/100))
    [[ $threshold_bytes -lt $diff_in_bytes ]] && echo "not restoring from backup because of amount of generated wals exceeds $THRESHOLD_PERCENTAGE% of cluster_size" && exit 1
fi

ATTEMPT=0
while true; do
    if $WAL_E backup-fetch "$DATA_DIR" LATEST; then
        version=$(<"$DATA_DIR/PG_VERSION")
        [[ "$version" =~ \. ]] && wal_name=xlog || wal_name=wal
        readonly wal_dir=$DATA_DIR/pg_$wal_name
        [[ ! -d $wal_dir ]] && rm -f "$wal_dir" && mkdir "$wal_dir"
        # remove broken symlinks from PGDATA
        find "$DATA_DIR" -xtype l -delete
        exit 0
    fi
    [[ $((ATTEMPT++)) -ge $RETRIES ]] && break
    rm -fr "$DATA_DIR"
    sleep 1
done

exit 1
