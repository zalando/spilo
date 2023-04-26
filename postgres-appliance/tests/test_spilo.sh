#!/bin/bash

cd "$(dirname "${BASH_SOURCE[0]}")" || exit 1

# shellcheck disable=SC1091
source ./test_utils.sh

readonly PREFIX="demo-"
readonly UPGRADE_SCRIPT="python3 /scripts/inplace_upgrade.py"
readonly TIMEOUT=120

function get_non_leader() {
    declare -r container=$1

    if [[ "$container" == "${PREFIX}spilo1" ]]; then
        echo "${PREFIX}spilo2"
    else
        echo "${PREFIX}spilo1"
    fi
}

function find_leader() {
    local container=$1
    local silent=$2
    declare -r timeout=$TIMEOUT
    local attempts=0

    while true; do
        leader=$(docker_exec "$container" 'patronictl list -f tsv' 2> /dev/null | awk '($4 == "Leader"){print $2}')
        if [[ -n "$leader" ]]; then
            [ -z "$silent" ] && echo "$leader"
            return
        fi
        ((attempts++))
        if [[ $attempts -ge $timeout ]]; then
            docker logs "$container"
            log_error "Leader is not running after $timeout seconds"
        fi
        sleep 1
    done
}

function wait_backup() {
    local container=$1

    declare -r timeout=$TIMEOUT
    local attempts=0

    # speed up backup creation
    local backup_starter_pid
    backup_starter_pid=$(docker exec "$container" pgrep -f '/bin/bash /scripts/patroni_wait.sh -t 3600 -- envdir /run/etc/wal-e.d/env /scripts/postgres_backup.sh')
    if [ -n "$backup_starter_pid" ]; then
        docker exec "$container" pkill -P "$backup_starter_pid" -f 'sleep 60'
    fi

    log_info "Waiting for backup on S3..,"

    sleep 1

    docker_exec -i "$1" "psql -U postgres -c CHECKPOINT" > /dev/null 2>&1

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
    wait_query "$1" "SELECT COUNT(*) FROM pg_stat_replication WHERE application_name LIKE 'spilo_' AND pg_catalog.pg_wal_lsn_diff(pg_catalog.pg_current_wal_lsn(), COALESCE(replay_lsn, '0/0')) < 16*1024*1024" 2
}

function create_schema() {
    docker_exec -i "$1" "psql -U postgres" < schema.sql
}

function create_schema2() {
    docker_exec -i "$1" "psql -U postgres" < schema2.sql
}

function drop_table_with_oids() {
    docker_exec "$1" "psql -U postgres -d test_db -c 'DROP TABLE with_oids'"
}

function drop_timescaledb() {
    docker_exec "$1" "psql -U postgres -d test_db -c 'DROP EXTENSION timescaledb CASCADE'"
}

function test_inplace_upgrade_wrong_version() {
    docker_exec "$1" "PGVERSION=10 $UPGRADE_SCRIPT 3" 2>&1 | grep 'Upgrade is not required'
}

function test_inplace_upgrade_wrong_capacity() {
    docker_exec "$1" "PGVERSION=11 $UPGRADE_SCRIPT 4" 2>&1 | grep 'number of replicas does not match'
}

function test_successful_inplace_upgrade_to_11() {
    docker_exec "$1" "PGVERSION=11 $UPGRADE_SCRIPT 3"
}

function test_envdir_suffix() {
    docker_exec "$1" "cat /run/etc/wal-e.d/env/WALG_S3_PREFIX" | grep -q "$2$" \
        && docker_exec "$1" "cat /run/etc/wal-e.d/env/WALE_S3_PREFIX" | grep -q "$2$"
}

function test_envdir_updated_to_x() {
    for c in {1..3}; do
        test_envdir_suffix "${PREFIX}spilo$c" "$1" || return 1
    done
}

function test_failed_inplace_upgrade_big_replication_lag() {
    ! test_successful_inplace_upgrade_to_11 "$1"
}

function test_successful_inplace_upgrade_to_13() {
    docker_exec "$1" "PGVERSION=13 $UPGRADE_SCRIPT 3"
}

function test_pg_upgrade_to_13_check_failed() {
    ! test_successful_inplace_upgrade_to_13 "$1"
}

function test_successful_inplace_upgrade_to_14() {
    docker_exec "$1" "PGVERSION=14 $UPGRADE_SCRIPT 3"
}

function test_successful_inplace_upgrade_to_15() {
    docker_exec "$1" "PGVERSION=15 $UPGRADE_SCRIPT 3"
}

function test_pg_upgrade_to_15_check_failed() {
    ! test_successful_inplace_upgrade_to_15 "$1"
}

function start_clone_with_wale_upgrade_container() {
    local ID=${1:-1}

    docker-compose run \
        -e SCOPE=upgrade \
        -e PGVERSION=11 \
        -e CLONE_SCOPE=demo \
        -e CLONE_METHOD=CLONE_WITH_WALE \
        -e CLONE_TARGET_TIME="$(date -d '1 minute' -u +'%F %T UTC')" \
        --name "${PREFIX}upgrade$ID" \
        -d "spilo$ID"
}

function start_clone_with_wale_upgrade_replica_container() {
    start_clone_with_wale_upgrade_container 2
}

function start_clone_with_wale_upgrade_to_15_container() {
    docker-compose run \
        -e SCOPE=upgrade3 \
        -e PGVERSION=15 \
        -e CLONE_SCOPE=demo \
        -e CLONE_PGVERSION=10 \
        -e CLONE_METHOD=CLONE_WITH_WALE \
        -e CLONE_TARGET_TIME="$(date -d '1 minute' -u +'%F %T UTC')" \
        --name "${PREFIX}upgrade4" \
        -d "spilo3"
}

function start_clone_with_wale_15_container() {
    docker-compose run \
        -e SCOPE=clone13 \
        -e PGVERSION=15 \
        -e CLONE_SCOPE=upgrade3 \
        -e CLONE_PGVERSION=15 \
        -e CLONE_METHOD=CLONE_WITH_WALE \
        -e CLONE_TARGET_TIME="$(date -d '1 hour' -u +'%F %T UTC')" \
        --name "${PREFIX}clone15" \
        -d "spilo3"
}

function start_clone_with_basebackup_upgrade_container() {
    local container=$1
    docker-compose run \
        -e SCOPE=upgrade2 \
        -e PGVERSION=12 \
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
    wait_query "$1" "SELECT current_setting('server_version_num')::int/10000" 11 2> /dev/null
}

function verify_clone_with_basebackup_upgrade() {
    log_info "Waiting for clone with basebackup and upgrade 11->12 to complete..."
    find_leader "$1" 1
    wait_query "$1" "SELECT current_setting('server_version_num')::int/10000" 12 2> /dev/null
}

function verify_clone_with_wale_upgrade_to_15() {
    log_info "Waiting for clone with wal-e and upgrade 10->15 to complete..."
    find_leader "$1" 1
    wait_query "$1" "SELECT current_setting('server_version_num')::int/10000" 15 2> /dev/null
}

function verify_archive_mode_is_on() {
    archive_mode=$(docker_exec "$1" "psql -U postgres -tAc \"SHOW archive_mode\"")
    [ "$archive_mode" = "on" ]
}


# TEST SUITE 1 - In-place major upgrade 10->11->...->15
# TEST SUITE 2 - Major upgrade 10->15 after wal-e clone
# TEST SUITE 3 - PITR (clone with wal-e) with unreachable target (13+)
# TEST SUITE 4 - Major upgrade 10->11 after wal-e clone
# TEST SUITE 5 - Replica bootstrap with wal-e
function test_spilo() {
    # TEST SUITE 1
    local container=$1

    run_test test_envdir_suffix "$container" 10

    run_test test_inplace_upgrade_wrong_version "$container"
    run_test test_inplace_upgrade_wrong_capacity "$container"

    wait_all_streaming "$container"

    create_schema "$container" || exit 1

    # run_test test_failed_inplace_upgrade_big_replication_lag "$container"

    wait_zero_lag "$container"
    run_test verify_archive_mode_is_on "$container"

    # TEST SUITE 2
    local upgrade_container
    upgrade_container=$(start_clone_with_wale_upgrade_to_15_container)
    log_info "Started $upgrade_container for testing major upgrade 10->15 after clone with wal-e"

    # TEST SUITE 1
    wait_backup "$container"

    log_info "Testing in-place major upgrade 10->11"
    run_test test_successful_inplace_upgrade_to_11 "$container"

    wait_all_streaming "$container"

    run_test test_envdir_updated_to_x 11

    create_schema2 "$container" || exit 1

    run_test test_pg_upgrade_to_13_check_failed "$container"  # pg_upgrade --check complains about OID

    # TEST SUITE 2
    run_test verify_clone_with_wale_upgrade_to_15 "$upgrade_container"

    run_test verify_archive_mode_is_on "$upgrade_container"
    wait_backup "$upgrade_container"
    docker rm -f "$upgrade_container"

    # TEST SUITE 3
    local clone15_container
    clone15_container=$(start_clone_with_wale_15_container)
    log_info "Started $clone15_container for testing point-in-time recovery (clone with wal-e) with unreachable target on 13+"

    # TEST SUITE 4
    upgrade_container=$(start_clone_with_wale_upgrade_container)
    log_info "Started $upgrade_container for testing major upgrade 10->11 after clone with wal-e"

    # TEST SUITE 1
    wait_backup "$container"
    wait_zero_lag "$container"

    drop_table_with_oids "$container"
    log_info "Testing in-place major upgrade 11->13"
    run_test test_successful_inplace_upgrade_to_13 "$container"

    wait_all_streaming "$container"

    run_test test_envdir_updated_to_x 13

    # TEST SUITE 3
    find_leader "$clone15_container"
    run_test verify_archive_mode_is_on "$clone15_container"

    # TEST SUITE 1
    wait_backup "$container"

    log_info "Testing in-place major upgrade to 13->14"
    run_test test_successful_inplace_upgrade_to_14 "$container"

    wait_all_streaming "$container"

    run_test test_envdir_updated_to_x 14

    # TEST SUITE 4
    log_info "Waiting for clone with wal-e and upgrade 10->11 to complete..."
    find_leader "$upgrade_container" 1
    run_test verify_clone_with_wale_upgrade "$upgrade_container"

    wait_backup "$upgrade_container"

    # TEST SUITE 5
    local upgrade_replica_container
    upgrade_replica_container=$(start_clone_with_wale_upgrade_replica_container)
    log_info "Started $upgrade_replica_container for testing replica bootstrap with wal-e"

    # TEST SUITE 4
    local basebackup_container
    basebackup_container=$(start_clone_with_basebackup_upgrade_container "$upgrade_container")
    log_info "Started $basebackup_container for testing major upgrade 11->12 after clone with basebackup"

    # TEST SUITE 1
    # run_test test_pg_upgrade_to_15_check_failed "$container"  # pg_upgrade --check complains about timescaledb

    wait_backup "$container"

    # drop_timescaledb "$container"

    log_info "Testing in-place major upgrade to 14->15"
    run_test test_successful_inplace_upgrade_to_15 "$container"

    wait_all_streaming "$container"

    run_test test_envdir_updated_to_x 15

    wait_backup "$container"

    # TEST SUITE 5
    log_info "Waiting for postgres to start in the $upgrade_replica_container..."
    run_test verify_clone_with_wale_upgrade "$upgrade_replica_container"

    # TEST SUITE 4
    run_test verify_clone_with_basebackup_upgrade "$basebackup_container"
    run_test verify_archive_mode_is_on "$basebackup_container"
}

function main() {
    stop_containers
    start_containers

    log_info "Waiting for leader..."
    local leader
    leader="$PREFIX$(find_leader "${PREFIX}spilo1")"
    test_spilo "$leader"
}

trap stop_containers QUIT TERM EXIT

main
