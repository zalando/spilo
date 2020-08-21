#!/usr/bin/env python
import json
import logging
import os
import psutil
import psycopg2
import shutil
import subprocess
import sys
import time
import yaml

logger = logging.getLogger(__name__)
CONFIG_FILE = os.path.join('/run/postgres.yml')


def update_configs(version):
    from spilo_commons import append_extentions, get_bin_dir, write_file

    with open(CONFIG_FILE) as f:
        config = yaml.safe_load(f)

    config['postgresql']['bin_dir'] = get_bin_dir(version)

    version = float(version)
    shared_preload_libraries = config['postgresql'].get('parameters', {}).get('shared_preload_libraries')
    if shared_preload_libraries is not None:
        config['postgresql']['parameters']['shared_preload_libraries'] =\
                append_extentions(shared_preload_libraries, version)

    extwlist_extensions = config['postgresql'].get('parameters', {}).get('extwlist.extensions')
    if extwlist_extensions is not None:
        config['postgresql']['parameters']['extwlist.extensions'] =\
                append_extentions(extwlist_extensions, version, True)

    write_file(yaml.dump(config, default_flow_style=False, width=120), CONFIG_FILE, True)

    # XXX: update wal-e env files


def kill_patroni():
    logger.info('Restarting patroni')
    patroni = next(iter(filter(lambda p: p.info['name'] == 'patroni', psutil.process_iter(['name']))), None)
    if patroni:
        patroni.kill()


class InplaceUpgrade(object):

    def __init__(self, config):
        from patroni.dcs import get_dcs
        from patroni.request import PatroniRequest
        from pg_upgrade import PostgresqlUpgrade

        self.config = config
        self.postgresql = PostgresqlUpgrade(config)

        self.cluster_version = self.postgresql.get_cluster_version()
        self.desired_version = self.get_desired_version()

        self.upgrade_required = float(self.cluster_version) < float(self.desired_version)

        self.paused = False
        self.new_data_created = False
        self.upgrade_complete = False
        self.rsyncd_configs_created = False
        self.rsyncd_started = False

        if self.upgrade_required:
            self.dcs = get_dcs(config)
            self.request = PatroniRequest(config)

    @staticmethod
    def get_desired_version():
        from spilo_commons import get_bin_dir, get_binary_version

        try:
            spilo_configuration = yaml.safe_load(os.environ.get('SPILO_CONFIGURATION', ''))
            bin_dir = spilo_configuration.get('postgresql', {}).get('bin_dir')
        except Exception:
            bin_dir = None

        if not bin_dir and os.environ.get('PGVERSION'):
            bin_dir = get_bin_dir(os.environ['PGVERSION'])

        return get_binary_version(bin_dir)

    def toggle_pause(self, paused):
        from patroni.utils import polling_loop

        cluster = self.dcs.get_cluster()
        config = cluster.config.data.copy()
        if cluster.is_paused() == paused:
            return logger.error('Cluster is %spaused, can not continue', ('' if paused else 'not '))

        config['pause'] = paused
        if not self.dcs.set_config_value(json.dumps(config, separators=(',', ':')), cluster.config.index):
            return logger.error('Failed to pause cluster, can not continue')

        self.paused = paused

        old = {m.name: m.index for m in cluster.members if m.api_url}
        ttl = cluster.config.data.get('ttl', self.dcs.ttl)
        for _ in polling_loop(ttl + 1):
            cluster = self.dcs.get_cluster()
            if all(m.data.get('pause', False) == paused for m in cluster.members if m.name in old):
                return True

        remaining = [m.name for m in cluster.members if m.data.get('pause', False) != paused
                     and m.name in old and old[m.name] != m.index]
        if remaining:
            return logger.error("%s members didn't recognized pause state after %s seconds", remaining, ttl)

    def ensure_replicas_state(self, cluster):
        self.replica_connections = {}
        streaming = {a: l for a, l in self.postgresql.query(
            ("SELECT client_addr, pg_catalog.pg_{0}_{1}_diff(pg_catalog.pg_current_{0}_{1}(),"
             " COALESCE(replay_{1}, '0/0'))::bigint FROM pg_catalog.pg_stat_replication")
            .format(self.postgresql.wal_name, self.postgresql.lsn_name))}

        def ensure_replica_state(member):
            ip = member.conn_kwargs().get('host')
            lag = streaming.get(ip)
            if lag is None:
                return logger.error('Member %s is not streaming from the primary', member.name)
            if lag > 16*1024*1024:
                return logger.error('Replication lag %s on member %s is to high', lag, member.name)

            # XXX check that Patroni REST API is accessible
            conn_kwargs = member.conn_kwargs(self.postgresql.config.superuser)
            for p in ['connect_timeout', 'options']:
                conn_kwargs.pop(p, None)

            conn = psycopg2.connect(**conn_kwargs)
            conn.autocommit = True
            cur = conn.cursor()
            cur.execute('SELECT pg_catalog.pg_is_in_recovery()')
            if not cur.fetchone()[0]:
                return logger.error('Member %s is not running as replica!', member.name)
            self.replica_connections[member.name] = (ip, cur)
            return True

        return all(ensure_replica_state(member) for member in cluster.members if member.name != self.postgresql.name)

    def sanity_checks(self, cluster):
        if not cluster.initialize:
            return logger.error('Upgrade can not be triggered because the cluster is no initialized')

        if len(cluster.members) != self.replica_count:
            return logger.error('Upgrade can not be triggered because the number of replicas does not match (%s != %s)',
                                len(cluster.members), self.replica_count)
        if cluster.is_paused():
            return logger.error('Upgrade can not be triggered because Patroni is in maintenance mode')

        lock_owner = cluster.leader and cluster.leader.name
        if lock_owner != self.postgresql.name:
            return logger.error('Upgrade can not be triggered because the current node does not own the leader lock')

        return self.ensure_replicas_state(cluster)

    def remove_initialize_key(self):
        from patroni.utils import polling_loop

        for _ in polling_loop(10):
            cluster = self.dcs.get_cluster()
            if cluster.initialize is None:
                return True
            logging.info('Removing initialize key')
            if self.dcs.cancel_initialization():
                return True
        logger.error('Failed to remove initialize key')

    def wait_for_replicas(self, checkpoint_lsn):
        from patroni.utils import polling_loop

        logger.info('Waiting for replica nodes to catch up with primary')

        query = ("SELECT pg_catalog.pg_{0}_{1}_diff(pg_catalog.pg_last_{0}_replay_{1}(),"
                 " '0/0')::bigint").format(self.postgresql.wal_name, self.postgresql.lsn_name)

        status = {}

        for _ in polling_loop(60):
            synced = True
            for name, (_, cur) in self.replica_connections.items():
                prev = status.get(name)
                if prev and prev >= checkpoint_lsn:
                    continue

                cur.execute(query)
                lsn = cur.fetchone()[0]
                status[name] = lsn

                if lsn < checkpoint_lsn:
                    synced = False

            if synced:
                logger.info('All replicas are ready')
                return True

        for name in self.replica_connections.keys():
            lsn = status.get(name)
            if not lsn or lsn < checkpoint_lsn:
                logger.error('Node %s did not catched up. Lag=%s', name, checkpoint_lsn - lsn)

    def create_rsyncd_configs(self):
        self.rsyncd_configs_created = True
        self.rsyncd_conf_dir = '/run/rsync'
        self.rsyncd_feedback_dir = os.path.join(self.rsyncd_conf_dir, 'feedback')

        if not os.path.exists(self.rsyncd_feedback_dir):
            os.makedirs(self.rsyncd_feedback_dir)

        self.rsyncd_conf = os.path.join(self.rsyncd_conf_dir, 'rsyncd.conf')
        secrets_file = os.path.join(self.rsyncd_conf_dir, 'rsyncd.secrets')

        auth_users = ','.join(self.replica_connections.keys())
        replica_ips = ','.join(str(v[0]) for v in self.replica_connections.values())

        with open(self.rsyncd_conf, 'w') as f:
            f.write("""port = 5432
use chroot = false

[pgroot]
path = {0}
read only = true
timeout = 300
post-xfer exec = echo $RSYNC_EXIT_STATUS > {1}/$RSYNC_USER_NAME
auth users = {2}
secrets file = {3}
hosts allow = {4}
hosts deny = *
""".format(os.path.dirname(self.postgresql.data_dir), self.rsyncd_feedback_dir, auth_users, secrets_file, replica_ips))

        with open(secrets_file, 'w') as f:
            for name in self.replica_connections.keys():
                f.write('{0}:{1}\n'.format(name, self.postgresql.config.replication['password']))
        os.chmod(secrets_file, 0o600)

    def start_rsyncd(self):
        self.create_rsyncd_configs()
        self.rsyncd = subprocess.Popen(['rsync', '--daemon', '--no-detach', '--config=' + self.rsyncd_conf])
        self.rsyncd_started = True

    def stop_rsyncd(self):
        if self.rsyncd_started:
            logger.info('Stopping rsyncd')
            try:
                self.rsyncd.kill()
                self.rsyncd_started = False
            except Exception as e:
                return logger.error('Failed to kill rsyncd: %r', e)

        if self.rsyncd_configs_created and os.path.exists(self.rsyncd_conf_dir):
            try:
                shutil.rmtree(self.rsyncd_conf_dir)
                self.rsyncd_configs_created = False
            except Exception as e:
                logger.error('Failed to remove %s: %r', self.rsync_conf_dir, e)

    def rsync_replicas(self, primary_ip):
        from patroni.utils import polling_loop

        # XXX: CHECKPOINT

        logger.info('Notifying replicas %s to start rsync', ','.join(self.replica_connections.keys()))
        ret = True
        status = {}
        for name, (ip, cur) in self.replica_connections.items():
            try:
                cur.execute("SELECT pg_catalog.pg_backend_pid()")
                pid = cur.fetchone()[0]
                cur.execute("COPY (SELECT) TO PROGRAM 'nohup {0} /scripts/inplace_upgrade.py {1} {2} {3}'"
                            .format(sys.executable, self.desired_version, primary_ip, pid))
                conn = cur.connection
                cur.close()
                conn.close()
            except Exception as e:
                logger.error('COPY TO PROGRAM on %s failed: %r', name, e)
                status[name] = False
                ret = False

        for name in status.keys():
            self.replica_connections.pop(name)

        logger.info('Waiting for replicas rsync complete')
        status.clear()
        for _ in polling_loop(300):
            synced = True
            for name in self.replica_connections.keys():
                feedback = os.path.join(self.rsyncd_feedback_dir, name)
                if name not in status and os.path.exists(feedback):
                    with open(feedback) as f:
                        status[name] = f.read().strip()
                else:
                    synced = False
            if synced:
                break

        for name in self.replica_connections.keys():
            result = status.get(name)
            if result is None:
                logger.error('Did not received rsync feedback from %s after 300 seconds', name)
                ret = False
            elif not result.startswith('0'):
                logger.error('Rsync on %s finished with code %s', name, result)
                ret = False
        return ret

    def do_upgrade(self):
        if not self.upgrade_required:
            logger.info('Current version=%s, desired version=%s. Upgrade is not required',
                        self.cluster_version, self.desired_version)
            return True

        if not (self.postgresql.is_running() and self.postgresql.is_leader()):
            return logger.error('PostgreSQL is not running or in recovery')

        cluster = self.dcs.get_cluster()

        if not self.sanity_checks(cluster):
            return False

        logger.info('Cluster %s is ready to be upgraded', self.postgresql.scope)
        if not self.postgresql.prepare_new_pgdata(self.desired_version):
            return logger.error('initdb failed')

        try:
            self.postgresql.drop_possibly_incompatible_objects()
        except Exception:
            return logger.error('Failed to drop possibly incompatible objects')

        # XXX: memorize and reset custom statistics target!

        logging.info('Enabling maintenance mode')
        if not self.toggle_pause(True):
            return False

        logger.info('Doing a clean shutdown of the cluster before pg_upgrade')
        if not self.postgresql.stop(block_callbacks=True):
            return logger.error('Failed to stop the cluster before pg_upgrade')

        checkpoint_lsn = int(self.postgresql.latest_checkpoint_location())
        logger.info('Latest checkpoint location: %s', checkpoint_lsn)

        logger.info('Starting rsyncd')
        self.start_rsyncd()

        if not self.wait_for_replicas(checkpoint_lsn):
            return False

        if not (self.rsyncd.pid and self.rsyncd.poll() is None):
            return logger.error('Failed to start rsyncd')

        if not self.postgresql.pg_upgrade():
            return logger.error('Failed to upgrade cluster from %s to %s', self.cluster_version, self.desired_version)

        self.postgresql.switch_pgdata()
        self.upgrade_complete = True

        logger.info('Updating configuration files')
        update_configs(self.desired_version)

        member = cluster.get_member(self.postgresql.name)
        primary_ip = member.conn_kwargs().get('host')
        try:
            ret = self.rsync_replicas(primary_ip)
        except Exception as e:
            logger.error('rsync failed: %r', e)
            ret = False

        self.stop_rsyncd()

        self.remove_initialize_key()
        kill_patroni()
        self.remove_initialize_key()

        time.sleep(2)  # XXX: check Patroni REST API is available
        logger.info('Starting the local postgres up')
        result = self.request(member, 'post', 'restart', {})
        logger.info('%s %s', result.status, result.data.decode('utf-8'))

        if self.paused:
            try:
                self.toggle_pause(False)
            except Exception as e:
                logger.error('Failed to resume cluster: %r', e)

        self.postgresql.analyze()
        self.postgresql.bootstrap.call_post_bootstrap(self.config['bootstrap'])
        self.postgresql.cleanup_old_pgdata()

        return ret

    def post_cleanup(self):
        self.stop_rsyncd()
        if self.paused:
            try:
                self.toggle_pause(False)
            except Exception as e:
                logger.error('Failed to resume cluster: %r', e)
        if self.new_data_created:
            try:
                self.postgresql.cleanup_new_pgdata()
            except Exception as e:
                logger.error('Failed to remove new PGDATA %r', e)

    def try_upgrade(self, replica_count):
        try:
            self.replica_count = replica_count
            return self.do_upgrade()
        finally:
            self.post_cleanup()


# this function will be running in a clean environment, therefore we can't rely on DCS connection
def rsync_replica(config, desired_version, primary_ip, pid):
    from pg_upgrade import PostgresqlUpgrade
    from patroni.utils import polling_loop

    backend = psutil.Process(pid)
    if 'postgres' not in backend.name():
        return 1

    postgresql = PostgresqlUpgrade(config)

    if postgresql.get_cluster_version() == desired_version:
        return 0

    if os.fork():
        return 0

    for _ in polling_loop(10):
        if not backend.is_running():
            break
    else:
        logger.warning('Backend did not exit after 10 seconds')

    sysid = postgresql.sysid  # remember old sysid

    if not postgresql.stop(block_callbacks=True):
        logger.error('Failed to stop the cluster before rsync')
        return 1

    postgresql.switch_pgdata()

    update_configs(desired_version)

    env = os.environ.copy()
    env['RSYNC_PASSWORD'] = postgresql.config.replication['password']
    if subprocess.call(['rsync', '--archive', '--delete', '--hard-links', '--size-only', '--no-inc-recursive',
                        '--include=/data/***', '--include=/data_old/***', '--exclude=*',
                        'rsync://{0}@{1}:5432/pgroot'.format(postgresql.name, primary_ip),
                        os.path.dirname(postgresql.data_dir)], env=env) != 0:
        logger.error('Failed to rsync from %s', primary_ip)
        postgresql.switch_back_pgdata()
        # XXX: rollback config?
        return 1

    conn_kwargs = {k: v for k, v in postgresql.config.replication.items() if v is not None}
    if 'username' in conn_kwargs:
        conn_kwargs['user'] = conn_kwargs.pop('username')

    for _ in polling_loop(300):
        try:
            with postgresql.get_replication_connection_cursor(primary_ip, **conn_kwargs) as cur:
                cur.execute('IDENTIFY_SYSTEM')
                if cur.fetchone()[0] != sysid:
                    break
        except Exception:
            pass

    postgresql.config.remove_recovery_conf()
    kill_patroni()
    postgresql.config.remove_recovery_conf()

    return postgresql.cleanup_old_pgdata()


def main():
    from patroni.config import Config

    config = Config(CONFIG_FILE)

    if len(sys.argv) == 4:
        desired_version = sys.argv[1]
        primary_ip = sys.argv[2]
        pid = int(sys.argv[3])
        return rsync_replica(config, desired_version, primary_ip, pid)
    elif len(sys.argv) == 2:
        replica_count = int(sys.argv[1])
        upgrade = InplaceUpgrade(config)
        return 0 if upgrade.try_upgrade(replica_count) else 1
    else:
        return 2


if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s upgrade_master %(levelname)s: %(message)s', level='INFO')
    sys.exit(main())
