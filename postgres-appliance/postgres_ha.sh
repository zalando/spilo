#!/bin/bash

PATH=$PATH:/usr/lib/postgresql/${PGVERSION}/bin

SSL_CERTIFICATE="$PGHOME/dummy.crt"
SSL_PRIVATE_KEY="$PGHOME/dummy.key"
BACKUP_INTERVAL=3600

function write_postgres_yaml
{
  local aws_private_ip=$(curl -s http://169.254.169.254/latest/meta-data/local-ipv4)
  local pg_port=5432
  local api_port=8008

  cat > postgres.yml <<__EOF__
ttl: &ttl 30
loop_wait: &loop_wait 10
scope: &scope $SCOPE
restapi:
  listen: 0.0.0.0:${api_port}
  connect_address: ${aws_private_ip}:${api_port}
__EOF__

  if [[ -n $ZOOKEEPER_HOSTS || -n $EXHIBITOR_HOSTS && -n $EXHIBITOR_PORT ]]; then
    cat >> postgres.yml <<__EOF__
zookeeper:
  scope: *scope
  session_timeout: *ttl
  reconnect_timeout: *loop_wait
__EOF__

    [[ -n $ZOOKEEPER_HOSTS ]] && echo "  hosts: ${ZOOKEEPER_HOSTS}" >> postgres.yml

    if [[ -n $EXHIBITOR_HOSTS && -n $EXHIBITOR_PORT ]]; then
      cat >> postgres.yml <<__EOF__
  exhibitor:
    poll_interval: 300
    port: ${EXHIBITOR_PORT}
    hosts: ${EXHIBITOR_HOSTS}
__EOF__
    fi
  elif [[ -n $ETCD_HOST ]]; then
    cat >> postgres.yml <<__EOF__
etcd:
  scope: *scope
  ttl: *ttl
  host: ${ETCD_HOST}
__EOF__
  elif [[ -n $ETCD_DISCOVERY_DOMAIN ]]; then
    cat >> postgres.yml <<__EOF__
etcd:
  scope: *scope
  ttl: *ttl
  discovery_srv: ${ETCD_DISCOVERY_DOMAIN}
__EOF__
  else
    >&2 echo "Can not find suitable distributed configuration store."
    exit 1
  fi

  cat >> postgres.yml <<__EOF__
postgresql:
  name: postgresql_${HOSTNAME}
  scope: *scope
  listen: 0.0.0.0:${pg_port}
  connect_address: ${aws_private_ip}:${pg_port}
  data_dir: $PGDATA
  pg_hba:
  - hostssl all all 0.0.0.0/0 md5
  - host    all all 0.0.0.0/0 md5
  replication:
    username: standby
    password: standby
    network: 0.0.0.0/0
  superuser:
    password: zalando
  admin:
    username: admin
    password: admin
  wal_e:
    env_dir: $WALE_ENV_DIR
    threshold_megabytes: ${WALE_BACKUP_THRESHOLD_MEGABYTES}
    threshold_backup_size_percentage: ${WALE_BACKUP_THRESHOLD_PERCENTAGE}
  restore: patroni/scripts/restore.py
  callbacks:
    on_start: patroni/scripts/aws.py
    on_stop: patroni/scripts/aws.py
    on_restart: patroni/scripts/aws.py
    on_role_change: patroni/scripts/aws.py
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
    ssl_cert_file: "$SSL_CERTIFICATE"
    ssl_key_file: "$SSL_PRIVATE_KEY"
  recovery_conf:
    restore_command: "envdir ${WALE_ENV_DIR} wal-e --aws-instance-profile wal-fetch \"%f\" \"%p\" -p 1"
__EOF__
}

function write_archive_command_environment
{
  mkdir -p ${WALE_ENV_DIR}
  echo "s3://${WAL_S3_BUCKET}/spilo/${SCOPE}/wal/" > ${WALE_ENV_DIR}/WALE_S3_PREFIX
}

write_postgres_yaml

if [[ ! -d "patroni" ]]
then
    # get patroni code
    git clone https://github.com/zalando/patroni.git
fi

write_archive_command_environment

# run wal-e s3 backup periodically
(
  INITIAL=1
  RETRY=0
  LAST_BACKUP_TS=0
  while true
  do
    sleep 5

    CURRENT_TS=$(date +%s)
    CURRENT_HOUR=$(date +%H)
    pg_isready >/dev/null 2>&2 || continue
    IN_RECOVERY=$(psql -tqAc "select pg_is_in_recovery()")

    [[ $IN_RECOVERY != "f" ]] && echo "still in recovery" && continue
    # during initial run, count the number of backup lines. If there are
    # no backup (only line with backup-list header is returned), or there
    # is an error, try to produce a backup. Otherwise, stick to the regular
    # schedule, since we might run the backups on a freshly promoted replica.
    if [[ $INITIAL = 1 ]]
    then
      BACKUPS_LINES=$(envdir ${WALE_ENV_DIR} wal-e --aws-instance-profile  backup-list 2>/dev/null|wc -l)
      [[ $PIPESTATUS[0] = 0 ]] && [[ $BACKUPS_LINES -ge 2 ]] && INITIAL=0
    fi
    # produce backup only at a given hour, unless it's set to *, which means
    # that only backup_interval is taken into account. We also skip all checks
    # when the backup is forced because of previous attempt's failure or because
    # it's going to be a very first backup, in which case we create it unconditionally.
    if [[ $RETRY = 0 ]] && [[ $INITIAL = 0 ]]
    then
      # check that enough time has passed since the previous backup
      [[ $BACKUP_HOUR != '*' ]] && [[ $CURRENT_HOUR != $BACKUP_HOUR ]] && continue
      # get the time since the last backup. Do it only one when the hour
      # matches the backup hour.
      [[ $LAST_BACKUP_TS = 0 ]] && LAST_BACKUP_TS=$(envdir ${WALE_ENV_DIR} wal-e --aws-instance-profile  backup-list LATEST 2>/dev/null | tail -n1 | awk '{print $2}' | xargs date +%s --date)
      # LAST_BACKUP_TS will be empty on error.
      if [[ -z $LAST_BACKUP_TS ]]
      then
        LAST_BACKUP_TS=0
        echo "could not obtain latest backup timestamp"
      fi

      ELAPSED_TIME=$((CURRENT_TS-LAST_BACKUP_TS))
      [[ $ELAPSED_TIME -lt $BACKUP_INTERVAL ]] && continue
    fi
    # leave only 2 base backups before creating a new one
    envdir ${WALE_ENV_DIR} wal-e --aws-instance-profile delete --confirm retain 2
    # push a new base backup
    echo "producing a new backup at $(date)"
    envdir ${WALE_ENV_DIR} wal-e --aws-instance-profile backup-push ${PGDATA}
    RETRY=$?
    # re-examine last backup timestamp if a new backup has been created
    if [[ $RETRY = 0 ]]
    then
      INITIAL=0
      LAST_BACKUP_TS=0
    fi
  done
) &

[[ "$DEBUG" == 1 ]] && exec /bin/bash
exec patroni/patroni.py "$PGHOME/postgres.yml"



