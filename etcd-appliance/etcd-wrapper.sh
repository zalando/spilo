#!/bin/bash

./update-dns-from-etcd.py &

ETCDDIR=( /etcd-v${ETCDVERSION}* )
cd "${ETCDDIR}"

## Use exec -c
## 1. etcd will be PID=1, therefore receiving signals from Docker
## 2. etcd will have a clean environment
exec -c ./etcd "$@"
