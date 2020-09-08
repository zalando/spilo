#!/bin/bash

cd "$(dirname "${BASH_SOURCE[0]}")" || exit 1

readonly PREFIX="demo-"
readonly UPGRADE_SCRIPT="python3 /scripts/inplace_upgrade.py"
readonly TIMEOUT=120

if [[ -t 2 ]]; then
    readonly RED="\033[1;31m"
    readonly RESET="\033[0m"
    readonly GREEN="\033[0;32m"
else
    readonly RED=""
    readonly RESET=""
    readonly GREEN=""
fi

function log_info() {
    echo -e "${GREEN}$*${RESET}"
}

function log_error() {
    echo -e "${RED}$*${RESET}"
    exit 1
}

function start_containers() {
    docker-compose up -d
}

function stop_containers() {
    docker-compose rm -fs
}

function get_non_leader() {
    declare -r container=$1

    if [[ "$container" == "${PREFIX}spilo1" ]]; then
        echo "${PREFIX}spilo2"
    else
        echo "${PREFIX}spilo1"
    fi
}

function docker_exec() {
    declare -r cmd=${*: -1:1}
    docker exec "${@:1:$(($#-1))}" su postgres -c "$cmd"
}

function find_leader() {
    local container=$1
    declare -r timeout=$TIMEOUT
    local attempts=0

    while true; do
        leader=$(docker_exec "$container" 'patronictl list -f tsv' 2> /dev/null | awk '($4 == "Leader"){print $2}')
        if [[ -n "$leader" ]]; then
            echo "$leader"
            return
        fi
        ((attempts++))
        if [[ $attempts -ge $timeout ]]; then
            log_error "Leader is not running after $timeout seconds"
        fi
        sleep 1
    done
}

function wait_backup() {
    local container=$1

    declare -r timeout=$TIMEOUT
    local attempts=0

    log_info "Waiting for backup on S3..,"
    while true; do
        count=$(docker_exec "$container" "envdir /run/etc/wal-e.d/env wal-g backup-list" | grep -c ^base)
        if [[ "$count" -gt 0 ]]; then
            return
        fi
        ((attempts++))
        if [[ $attempts -ge $timeout ]]; then
            log_error "No backup produced after $timeout seconds"
        fi
        sleep 1
    done
}

function wait_query() {
    local container=$1
    local query=$2
    local result=$3

    declare -r timeout=$TIMEOUT
    local attempts=0

    while true; do
        ret=$(docker_exec "$container" "psql -U postgres -tAc \"$query\"")
        if [[ "$ret" = "$result" ]]; then
            return 0
        fi
        ((attempts++))
        if [[ $attempts -ge $timeout ]]; then
            log_error "Query \"$query\" didn't return expected result $result after $timeout seconds"
        fi
        sleep 1
    done
}

function wait_all_streaming() {
    log_info "Waiting for all replicas to start streaming from the leader..."
    wait_query "$1" "SELECT COUNT(*) FROM pg_stat_replication WHERE application_name LIKE 'spilo_'" 2
}

function wait_zero_lag() {
    log_info "Waiting for all replicas to catch up with WAL replay..."
    wait_query "$1" "SELECT COUNT(*) FROM pg_stat_replication WHERE application_name LIKE 'spilo_' AND pg_catalog.pg_xlog_location_diff(pg_catalog.pg_current_xlog_location(), COALESCE(replay_location, '0/0')) < 16*1024*1024" 2
}

function create_schema() {
    docker_exec -i "$1" "psql -U postgres" < schema.sql
}

function drop_table_with_oids() {
    docker_exec "$1" "psql -U postgres -d test_db -c 'DROP TABLE with_oids'"
}

function test_upgrade_wrong_container() {
    ! docker_exec "$(get_non_leader "$1")" "PGVERSION=10 $UPGRADE_SCRIPT 4"
}

function test_upgrade_wrong_version() {
    docker_exec "$1" "PGVERSION=9.5 $UPGRADE_SCRIPT 3" 2>&1 | grep 'Upgrade is not required'
}

function test_upgrade_wrong_capacity() {
    docker_exec "$1" "PGVERSION=10 $UPGRADE_SCRIPT 4" 2>&1 | grep 'number of replicas does not match'
}

function test_successful_upgrade_to_10() {
    docker_exec "$1" "PGVERSION=10 $UPGRADE_SCRIPT 3"
}

function test_failed_upgrade_big_replication_lag() {
    ! test_successful_upgrade_to_10 "$1"
}

function test_successful_upgrade_to_12() {
    docker_exec "$1" "PGVERSION=12 $UPGRADE_SCRIPT 3"
}

function test_pg_upgrade_check_failed() {
    ! test_successful_upgrade_to_12 "$1"
}

function start_clone_with_wale_upgrade_container() {
    docker-compose run \
        -e SCOPE=upgrade \
        -e PGVERSION=10 \
        -e CLONE_SCOPE=demo \
        -e CLONE_METHOD=CLONE_WITH_WALE \
        -e CLONE_TARGET_TIME="$(date -d '1 minute' -u +'%F %T UTC')" \
        --name "${PREFIX}upgrade1" \
        -d spilo1
}

function start_clone_with_wale_upgrade_replica_container() {
    docker-compose run \
        -e SCOPE=upgrade \
        -e PGVERSION=10 \
        -e CLONE_SCOPE=demo \
        -e CLONE_METHOD=CLONE_WITH_WALE \
        -e CLONE_TARGET_TIME="$(date -d '1 minute' -u +'%F %T UTC')" \
        --name "${PREFIX}upgrade2" \
        -d spilo2
}
function start_clone_with_basebackup_upgrade_container() {
    local container=$1
    docker-compose run \
        -e SCOPE=upgrade2 \
        -e PGVERSION=11 \
        -e CLONE_SCOPE=upgrade \
        -e CLONE_METHOD=CLONE_WITH_BASEBACKUP \
        -e CLONE_HOST="$(docker_exec "$container" "hostname --ip-address")" \
        -e CLONE_PORT=5432 \
        -e CLONE_USER=standby \
        -e CLONE_PASSWORD=standby \
        --name "${PREFIX}upgrade3" \
        -d spilo3
}

function verify_clone_with_wale_upgrade() {
    wait_query "$1" "SELECT current_setting('server_version_num')::int/10000" 10
}

function verify_clone_with_basebackup_upgrade() {
    wait_query "$1" "SELECT current_setting('server_version_num')::int/10000" 11
}

function run_test() {
    "$@" || log_error "Test case $1 FAILED"
    echo -e "Test case $1 ${GREEN}PASSED${RESET}"
}

function test_upgrade() {
    local container=$1

    run_test test_upgrade_wrong_version "$container"
    run_test test_upgrade_wrong_capacity "$container"

    wait_all_streaming "$container"

    run_test test_upgrade_wrong_container "$container"

    create_schema "$container" || exit 1
#    run_test test_failed_upgrade_big_replication_lag "$container"

    wait_zero_lag "$container"
    wait_backup "$container"

    local upgrade_container
    upgrade_container=$(start_clone_with_wale_upgrade_container)
    log_info "Started $upgrade_container for testing major upgrade after clone with wal-e"

    run_test test_successful_upgrade_to_10 "$container"

    wait_all_streaming "$container"
    run_test test_pg_upgrade_check_failed "$container"  # pg_upgrade --check complains about OID

    drop_table_with_oids "$container"
    run_test test_successful_upgrade_to_12 "$container"

    log_info "Waiting for clone with wal-e and upgrade to complete..."
    find_leader "$upgrade_container" > /dev/null
    docker logs "$upgrade_container"
    run_test verify_clone_with_wale_upgrade "$upgrade_container"

    wait_backup "$upgrade_container"

    local upgrade_replica_container
    upgrade_replica_container=$(start_clone_with_wale_upgrade_replica_container)
    log_info "Started $upgrade_replica_container for testing replica bootstrap with wal-e"

    local basebackup_container
    basebackup_container=$(start_clone_with_basebackup_upgrade_container "$upgrade_container")
    log_info "Started $basebackup_container for testing major upgrade after clone with basebackup"

    log_info "Waiting for postgres to start in the $upgrade_replica_container..."
    run_test verify_clone_with_wale_upgrade "$upgrade_replica_container"

    log_info "Waiting for clone with basebackup and upgrade to complete..."
    find_leader "$basebackup_container" > /dev/null
    docker logs "$basebackup_container"
    run_test verify_clone_with_basebackup_upgrade "$basebackup_container"
}

function main() {
    stop_containers
    start_containers

    log_info "Waiting for leader..."
    local leader
    leader="$PREFIX$(find_leader "${PREFIX}spilo1")"
    test_upgrade "$leader"
}

trap stop_containers QUIT TERM EXIT

main
