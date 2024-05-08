#!/bin/bash

if ! docker info &> /dev/null; then
    if podman info &> /dev/null; then
        alias docker=podman
        alias xargs='xargs '  # allows '| xargs docker'
        shopt -s expand_aliases
    else
        echo "docker/podman: command not found"
        exit 1
    fi
fi

set -a

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

function next_minute() {
    date -d '1 minute' -u +'%F %T UTC' 2>/dev/null || date -v+1M -u +'%F %T UTC'
}

function next_hour() {
    date -d '1 hour' -u +'%F %T UTC' 2>/dev/null || date -v+1H -u +'%F %T UTC'
}

function start_containers() {
    docker-compose up -d
}

function stop_containers() {
    docker-compose rm -fs
}

function rm_container() {
    docker rm -f "$1"
}

function docker_exec() {
    declare -r cmd=${*: -1:1}
    docker exec "${@:1:$(($#-1))}" su postgres -c "$cmd"
}

function run_test() {
    "$@" || log_error "Test case $1 FAILED"
    echo -e "Test case $1 ${GREEN}PASSED${RESET}"
}
