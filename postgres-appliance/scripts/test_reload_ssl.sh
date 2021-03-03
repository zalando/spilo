#!/bin/bash
#
# This script is being called every TEST_INTERVAL_MINUTES to check if the
# spilo or postgres configuration need to be reloaded.
#
# Usage: test_reload_ssl.sh <TEST_INTERVAL_MINUTES>
set -euo pipefail

# How often this script is being called
test_interval_min=$1
test_interval_sec=$((test_interval_min * 60))

## Functions ##

log() {
    echo "$*" >&2
}

has_changed() {
    local env=$1
    local path=${!1:-}
    if [[ -z "$path" ]]; then
        log "env=$env: environment is not set"
        return 1
    fi
    if [[ ! -e "$path" ]]; then
        log "env=$env path=$path: does not exist"
        return 1
    fi
    local mtime now elapsed_sec
    mtime=$(stat -Lc '%Y' "$path")
    now=$(date +%s)
    elapsed_sec=$(( now - 1 - mtime ))
    if [[ $elapsed_sec -gt $test_interval_sec ]]; then
        log "env=$env path=$path elapsec_sec=$elapsed_sec: no changes detected"
        return 1
    fi
    log "env=$env path=$path elapsec_sec=$elapsed_sec: found changes"
    return 0
}

## Main ##

if
    has_changed SSL_CA_FILE || \
    has_changed SSL_CRL_FILE || \
    has_changed SSL_CERTIFICATE_FILE || \
    has_changed SSL_PRIVATE_KEY_FILE
then
    log "Reloading due to detected changes"
    pg_ctl reload
fi
