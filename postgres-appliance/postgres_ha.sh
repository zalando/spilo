#!/bin/bash

PATH=$PATH:/usr/lib/postgresql/${PGVERSION}/bin
WALE_ENV_DIR=/home/postgres/etc/wal-e.d/env

SSL_CERTIFICATE="/home/postgres/dummy.crt"
SSL_PRIVATE_KEY="/home/postgres/dummy.key"

function write_postgres_yaml
{
  aws_private_ip=$(curl -s http://169.254.169.254/latest/meta-data/local-ipv4)
  cat >> postgres.yml <<__EOF__
loop_wait: 10
etcd:
  scope: $SCOPE
  ttl: 30
  host: 127.0.0.1:2379
postgresql:
  name: postgresql_${HOSTNAME}
  listen: 0.0.0.0:5432
  connect_address: ${aws_private_ip}:5432
  data_dir: $PGDATA
  replication:
    username: standby
    password: standby
    network: 0.0.0.0/0
  superuser:
    password: zalando
  admin:
    username: admin
    password: admin
  parameters:
    archive_mode: "on"
    wal_level: hot_standby
    archive_command: "envdir ${WALE_ENV_DIR} wal-e --aws-instance-profile wal-push \"%p\" -p 1"
    max_wal_senders: 5
    wal_keep_segments: 8
    archive_timeout: 1800s
    max_replication_slots: 5
    hot_standby: "on"
	ssl: "on"
  recovery_conf:
    restore_command: "envdir ${WALE_ENV_DIR} wal-e --aws-instance-profile wal-fetch \"%f\" \"%p\" -p 1"
__EOF__
}

function write_archive_command_environment
{
  mkdir -p ${WALE_ENV_DIR}
  echo "s3://${WAL_S3_BUCKET}/spilo/${SCOPE}/wal/" > ${WALE_ENV_DIR}/WALE_S3_PREFIX
}

# get governor code
git clone https://github.com/zalando/governor.git

write_postgres_yaml

write_archive_command_environment

# start etcd proxy
# for the -proxy on TDB the url of the etcd cluster
[ "$DEBUG" -eq 1 ] && exec /bin/bash

etcd -name "proxy-$SCOPE" -proxy on --data-dir=etcd -discovery-srv $ETCD_DISCOVERY_URL &

exec governor/governor.py "/home/postgres/postgres.yml"



