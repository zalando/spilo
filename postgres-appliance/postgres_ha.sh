#!/bin/bash

PATH=$PATH:/usr/lib/postgresql/${PGVERSION}/bin

function write_postgres_yaml
{
  cat >> postgres.yml <<__EOF__
loop_wait: 10
etcd:
  scope: $SCOPE
  ttl: 30
  host: 127.0.0.1:8080
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

write_postgres_yaml

# start etcd proxy
# for the -proxy on TDB the url of the etcd cluster
if [ "$DEBUG" -eq 1 ]
then
  exec /bin/bash
fi
etcd -name "proxy-$SCOPE" -proxy on -bind-addr 127.0.0.1:8080 --data-dir=data/etcd -initial-cluster $ETCD_CLUSTER &

exec governor/governor.py "/home/postgres/postgres.yml"



