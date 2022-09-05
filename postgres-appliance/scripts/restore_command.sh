#!/bin/bash

if [[ "$ENABLE_WAL_PATH_COMPAT" = "true" ]]; then
    unset ENABLE_WAL_PATH_COMPAT
    bash "$(readlink -f "${BASH_SOURCE[0]}")" "$@"
    exitcode=$?
    [[ $exitcode = 0 ]] && exit 0
    for wale_env in $(printenv -0 | tr '\n' ' ' | sed 's/\x00/\n/g' | sed -n 's/^\(WAL[EG]_[^=][^=]*_PREFIX\)=.*$/\1/p'); do
        suffix=$(basename "${!wale_env}")
        if [[ -x "/usr/lib/postgresql/$suffix/bin/postgres" ]]; then
            prefix=$(dirname "${!wale_env}")
            if [[ $prefix =~ /spilo/ ]] && [[ $prefix =~ /wal$ ]]; then
                printf -v "$wale_env" "%s" "$prefix"
                # shellcheck disable=SC2163
                export "$wale_env"
                changed_env=true
            fi
        fi
    done
    [[ "$changed_env" == "true" ]] || exit $exitcode
fi

readonly wal_filename=$1
readonly wal_destination=$2

[[ -z $wal_filename || -z $wal_destination ]] && exit 1

wal_dir=$(dirname "$wal_destination")
readonly wal_dir
wal_fast_source=$(dirname "$(dirname "$(realpath "$wal_dir")")")/wal_fast/$wal_filename
readonly wal_fast_source

[[ -f $wal_fast_source ]] && exec mv "${wal_fast_source}" "${wal_destination}"

if [[ "$wal_destination" =~ /$wal_filename$ ]]; then  # Patroni fetching missing files for pg_rewind
    export WALG_DOWNLOAD_CONCURRENCY=1
    POOL_SIZE=0
else
    POOL_SIZE=$WALG_DOWNLOAD_CONCURRENCY
fi

[[ "$USE_WALG_RESTORE" == "true" ]] && exec wal-g wal-fetch "${wal_filename}" "${wal_destination}"

[[ $POOL_SIZE -gt 8 ]] && POOL_SIZE=8

if [[ -z $WALE_S3_PREFIX ]]; then  # non AWS environment?
    readonly wale_prefetch_source=${wal_dir}/.wal-e/prefetch/${wal_filename}
    if [[ -f $wale_prefetch_source ]]; then
        exec mv "${wale_prefetch_source}" "${wal_destination}"
    else
        exec wal-e wal-fetch -p $POOL_SIZE "${wal_filename}" "${wal_destination}"
    fi
else
    exec bash /scripts/wal-e-wal-fetch.sh wal-fetch -p $POOL_SIZE "${wal_filename}" "${wal_destination}"
fi
