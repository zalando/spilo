#!/bin/bash
#
# This script is called to check if the spilo or postgres configuration need to
# be reloaded due to changes in TLS files.
#
# Usage: test_reload_ssl.sh <STORED_HASH_DIRECTORY>
set -euo pipefail

# Directory where hashes for each SSL file are stored
last_hash_dir=$1

# Redirect output to a log file
# exec >$last_hash_dir/test_reload_ssl.log 2>&1
# NOW="$(date)"
# LOGNAME="$last_hash_dir/test_reload_ssl.log."${NOW}
# exec > "$LOGNAME" 2>&1

# The hash command to use
hash_cmd="sha256sum"

## Functions ##

log() {
    echo "$*" >&2
}

has_changed() {
    local env=$1
    local src_path=${!1:-}
    local hash_path="$last_hash_dir/${env}.hash"
    local live_hash
    local last_hash

    if [[ -z "$src_path" ]]; then
        log "env=$env: environment is not set"
        return 1
    fi
    if [[ ! -e "$src_path" ]]; then
        log "env=$env src_path=$src_path: does not exist"
        return 1
    fi
    if [[ ! -e "$hash_path" ]]; then
        log "env=$env hash_path=$hash_path: does not exist yet"
        return 0
    fi

    live_hash=$($hash_cmd "$src_path")
    last_hash=$(cat "$hash_path")

    if [[ $live_hash = "$last_hash" ]]; then
        log "env=$env path=$src_path live_hash=$live_hash: no changes detected"
        return 1
    fi
    log "env=$env path=$src_path live_hash=$live_hash last_hash=$last_hash: found changes"
    return 0
}

write_hash() {
    local env=$1
    local src_path=${!1:-}
    local hash_path="$last_hash_dir/${env}.hash"

    if [[ ! -e "$src_path" ]]; then
        log "env=$env src_path=$src_path: does not exist; skipped writing hash"
        return 0
    fi

    $hash_cmd "$src_path" > "$hash_path"
}

write_hashes() {
    write_hash SSL_CA_FILE
    write_hash SSL_CRL_FILE
    write_hash SSL_CERTIFICATE_FILE
    write_hash SSL_PRIVATE_KEY_FILE
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
    write_hashes
fi
