#!/bin/bash

# This is a very simple wrapper script to run pgbackrest only if the server is not in recovery mode.
# I is used in the crontabs, to avoid failing crons due to the server being in recovery mode.
IN_RECOVERY=$(psql -tXqAc "select pg_catalog.pg_is_in_recovery()")
readonly IN_RECOVERY
if [[ $IN_RECOVERY == "f" ]]; then
  exec pgbackrest "$@"
fi
exit 0
