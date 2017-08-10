#!/bin/bash

readonly xlog_filename=$1
readonly xlog_destination=$2

[[ -z $xlog_filename || -z $xlog_destination ]] && exit 1

readonly xlog_dir=$(dirname $xlog_destination)
readonly xlog_fast_source=$(dirname $(dirname $(realpath $xlog_dir)))/xlog_fast/$xlog_filename

[[ -f $xlog_fast_source ]] && exec mv "${xlog_fast_source}" "${xlog_destination}"

POOL_SIZE=$(($(nproc)-1))
[[ $POOL_SIZE -gt 8 ]] && POOL_SIZE=8

if [[ -z $WALE_S3_PREFIX ]]; then  # non AWS environment?
    readonly wale_prefetch_source=${xlog_dir}/.wal-e/prefetch/${xlog_filename}
    if [[ -f $wale_prefetch_source ]]; then
        exec mv "${wale_prefetch_source}" "${xlog_destination}"
    else
        exec wal-e wal-fetch -p $POOL_SIZE "${xlog_filename}" "${xlog_destination}"
    fi
else
    exec /wal-e-wal-fetch.sh --aws-instance-profile wal-fetch -p $POOL_SIZE "${xlog_filename}" "${xlog_destination}"
fi
