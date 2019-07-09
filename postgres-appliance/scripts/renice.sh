#!/bin/bash

set -Eeuo pipefail

# we don't need to use procps utils because bg_mon already "knows" all postgres processes
curl -s http://localhost:8080 \
    | jq '.processes[] | select(
                .type == "checkpointer"
             or .type == "archiver"
             or .type == "startup"
             or .type == "walsender"
             or .type == "walreceiver"
          ) | .pid' \
    | xargs renice -n -20 -p &> /tmp/renice.log
