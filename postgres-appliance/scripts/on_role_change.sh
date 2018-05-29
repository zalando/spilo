#!/bin/bash

readonly HUMAN_ROLE=$1
shift

"$@"


readonly dbname=postgres
if [[ "${*: -3:1}" == "on_role_change" && "${*: -2:1}" == "master" ]]; then
    num=30  # wait 30 seconds for end of recovery
    while  [[ $((num--)) -gt 0 ]]; do
        if [[ "$(psql -d $dbname -tAc 'SELECT pg_is_in_recovery()')" == "f" ]]; then
            exec /scripts/post_init.sh "$HUMAN_ROLE" "$dbname"
        else
            sleep 1
        fi
    done
fi
