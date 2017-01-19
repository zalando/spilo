#!/bin/bash

readonly xlog_filename=$1
readonly xlog_destination=$2

[[ -z $xlog_filename || -z $xlog_destination ]] && exit 1

readonly xlog_dir=$(dirname $xlog_destination)
readonly xlog_fast_source=$(dirname $(dirname $(realpath $xlog_dir)))/xlog_fast/$xlog_filename
readonly wale_prefetch_source=${xlog_dir}/.wal-e/prefetch/${xlog_filename}

if [[ -f $xlog_fast_source ]]; then
    exec mv "${xlog_fast_source}" "${xlog_destination}"
elif [[ -f $wale_prefetch_source ]]; then
    exec mv "${wale_prefetch_source}" "${xlog_destination}"
else
    exec wal-e --aws-instance-profile wal-fetch "${xlog_filename}" "${xlog_destination}"
fi
