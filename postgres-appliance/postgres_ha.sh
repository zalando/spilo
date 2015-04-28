#!/bin/bash

PATH=$PATH:/usr/lib/postgresql/${PGVERSION}/bin

function write_postgres_yaml
{
  local_address=$(cat /etc/hosts |grep ${HOSTNAME}|cut -f1)
  cat >> postgres.yml <<__EOF__
loop_wait: 10
etcd:
  scope: $SCOPE
  ttl: 30
  host: 127.0.0.1:8080
postgresql:
  name: postgresql_${HOSTNAME}
  listen: ${local_address}:5432
  data_dir: $PGDATA
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
    hot_standby: "on"
__EOF__
}

# get governor code
git clone https://github.com/zalando/governor.git

write_postgres_yaml

# start etcd proxy
# for the -proxy on TDB the url of the etcd cluster
[ "$DEBUG" -eq 1 ] && exec /bin/bash

if [[ -n $ETCD_ADDRESS ]]
then
  # address is still useful for local debugging
  etcd -name "proxy-$SCOPE" -proxy on -bind-addr 127.0.0.1:8080 --data-dir=etcd -initial-cluster $ETCD_ADDRESS &
else
  etcd -name "proxy-$SCOPE" -proxy on -bind-addr 127.0.0.1:8080 --data-dir=etcd -discovery-srv $ETCD_DISCOVERY_URL &
fi

exec governor/governor.py "/home/postgres/postgres.yml"



