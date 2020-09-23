#!/bin/bash

readonly wal_filename=$1
readonly wal_destination=$2

[[ -z $wal_filename || -z $wal_destination ]] && exit 1

readonly wal_dir=$(dirname "$wal_destination")
readonly wal_fast_source=$(dirname "$(dirname "$(realpath "$wal_dir")")")/wal_fast/$wal_filename

[[ -f $wal_fast_source ]] && exec mv "${wal_fast_source}" "${wal_destination}"

if [[ "$wal_destination" =~ /$wal_filename$ ]]; then  # Patroni fetching missing files for pg_rewind
    export WALG_DOWNLOAD_CONCURRENCY=1
fi

[[ "$USE_WALG_RESTORE" == "true" ]] && exec wal-g wal-fetch "${wal_filename}" "${wal_destination}"

[[ $WALG_DOWNLOAD_CONCURRENCY -gt 8 ]] && WALG_DOWNLOAD_CONCURRENCY=8

if [[ -z $WALE_S3_PREFIX ]]; then  # non AWS environment?
    readonly wale_prefetch_source=${wal_dir}/.wal-e/prefetch/${wal_filename}
    if [[ -f $wale_prefetch_source ]]; then
        exec mv "${wale_prefetch_source}" "${wal_destination}"
    else
        exec wal-e wal-fetch -p $WALG_DOWNLOAD_CONCURRENCY "${wal_filename}" "${wal_destination}"
    fi
else
    exec bash /scripts/wal-e-wal-fetch.sh wal-fetch -p $WALG_DOWNLOAD_CONCURRENCY "${wal_filename}" "${wal_destination}"
fi
