#!/bin/bash

PATH=$PATH:/usr/lib/postgresql/${PGVERSION}/bin

function write_postgres_yaml
{
  local SCOPE=$1
  cat >> postgres.yml <<__EOF__
loop_wait: 10
etcd:
  scope: $SCOPE
  ttl: 30
  host: 127.0.0.1:4001
postgresql:
  name: postgresql-${hostname}
  listen: 0.0.0.0:5432
  data_dir: $PGDATA/data
  replication:
    username: standby
    password: standby
    network: 0.0.0.0/0
  parameters:
    archive_mode: "on"
    wal_level: hot_standby
    archive_command: /bin/true
    max_wal_senders: 5
    wal_keep_segments: 8
    archive_timeout: 1800s
    max_replication_slots: 5
__EOF__
}

# get governor code
git clone https://github.com/compose/governor.git

# start etcd proxy
# for the -proxy on TDB the url of the etcd cluster
etcd --data-dir=data/etcd &

write_postgres_yaml "$@"
#exec "/bin/bash"
exec governor/governor.py "/home/postgres/postgres.yml"



