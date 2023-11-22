#!/usr/bin/env python
"""spilo ``--update-version`` machinery."""
import json
import logging
import os
import psutil
import psycopg2
import shlex
import shutil
import subprocess
import sys
import time
import yaml

from collections import defaultdict
from threading import Thread
from multiprocessing.pool import ThreadPool

logger = logging.getLogger(__name__)

RSYNC_PORT = 5432


def patch_wale_prefix(value, new_version):
    """
    Patch the WAL prefix with the new version if the old version is valid and different from the new version.

    :param value: The WAL prefix to patch.
    :param new_version: The new version to use.

    Returns:
        str: The patched WAL prefix if the old version is valid and different from the new version, otherwise the original value.
    """
    from spilo_commons import is_valid_pg_version

    if '/spilo/' in value and '/wal/' in value:  # path crafted in the configure_spilo.py?
        basename, old_version = os.path.split(value.rstrip('/'))
        if is_valid_pg_version(old_version) and old_version != new_version:
            return os.path.join(basename, new_version)
    return value


def update_configs(new_version):
    """
    Update the Patroni configuration file by setting the new Postgres version and updating the shared_preload_libraries.
    Update the WAL-E/WAL-G envdir files by patching the WAL prefix with the new version if the old version is valid and different from the new version.
    Checks if the extwlist.extensions parameter is set in the Patroni configuration file and appends the new extensions to it.
    Writes the update Patroni configuration file and WAL-E/WAL-G envdir files.
    
    :param new_version: The new Postgres version to be upgrade.
    
    Returns: The path to the WAL-E/WAL-G envdir files if they exist, None otherwise.
    """
    from spilo_commons import append_extensions, get_bin_dir, get_patroni_config, write_file, write_patroni_config

    config = get_patroni_config()

    config['postgresql']['bin_dir'] = get_bin_dir(new_version)

    version = float(new_version)
    shared_preload_libraries = config['postgresql'].get('parameters', {}).get('shared_preload_libraries')
    if shared_preload_libraries is not None:
        config['postgresql']['parameters']['shared_preload_libraries'] =\
                append_extensions(shared_preload_libraries, version)

    extwlist_extensions = config['postgresql'].get('parameters', {}).get('extwlist.extensions')
    if extwlist_extensions is not None:
        config['postgresql']['parameters']['extwlist.extensions'] =\
                append_extensions(extwlist_extensions, version, True)

    write_patroni_config(config, True)

    # update wal-e/wal-g envdir files
    restore_command = shlex.split(config['postgresql'].get('recovery_conf', {}).get('restore_command', ''))
    if len(restore_command) > 6 and restore_command[0] == 'envdir':
        envdir = restore_command[1]

        try:
            for name in os.listdir(envdir):
                # len('WALE__PREFIX') = 12
                if len(name) > 12 and name.endswith('_PREFIX') and name[:5] in ('WALE_', 'WALG_'):
                    name = os.path.join(envdir, name)
                    try:
                        with open(name) as f:
                            value = f.read().strip()
                        new_value = patch_wale_prefix(value, new_version)
                        if new_value != value:
                            write_file(new_value, name, True)
                    except Exception as e:
                        logger.error('Failed to process %s: %r', name, e)
        except Exception:
            pass
        else:
            return envdir


def kill_patroni():
    """
    Restarts the Patroni process.

    This function finds the Patroni process and kills it. If the process is not found, nothing happens.
    """
    logger.info('Restarting patroni')
    patroni = next(iter(filter(lambda p: p.info['name'] == 'patroni', psutil.process_iter(['name']))), None)
    if patroni:
        patroni.kill()


class InplaceUpgrade(object):
    """
    A class representing an in-place upgrade of a PostgreSQL cluster.

        :ivar config: a dictionary containing the configuration parameters for the upgrade process.
        :ivar postgresql: a PostgresqlUpgrade object representing the PostgreSQL instance being upgraded.
        :ivar cluster_version: the version of the PostgreSQL cluster being upgraded.
        :ivar desired_version: the version of PostgreSQL to which the cluster is being upgraded.
        :ivar upgrade_required: a flag indicating whether an upgrade is required.
        :ivar paused: a flag indicating whether the upgrade process is currently paused.
        :ivar new_data_created: a flag indicating whether new data has been created during the upgrade process.
        :ivar upgrade_complete: a flag indicating whether the upgrade process has been completed.
        :ivar rsyncd_configs_created: a flag indicating whether rsyncd configurations have been created during the upgrade process.
        :ivar rsyncd_started: a flag indicating whether rsyncd has been started during the upgrade process.
        :ivar dcs: a distributed configuration store object.
        :ivar request: a PatroniRequest object representing a request to the PostgreSQL cluster.
    """

    def __init__(self, config):
        """
        Initializes the InplaceUpgrade object.

        :param config: a dictionary containing the configuration parameters for the upgrade process.
        """
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
            # we want to reduce tcp timeouts and keepalives and therefore tune loop_wait, retry_timeout, and ttl
            self.dcs = get_dcs({**config.copy(), 'loop_wait': 0, 'ttl': 10, 'retry_timeout': 10, 'patronictl': True})
            self.request = PatroniRequest(config, True)

    @staticmethod
    def get_desired_version():
        """
        Returns the desired version of the PostgreSQL binary to be used for the upgrade.

        This function first attempts to retrieve the binary directory from the SPILO_CONFIGURATION environment variable.
        If that fails, it retrieves the binary directory from the PGVERSION environment variable.
        Finally, it returns the version of the PostgreSQL binary located in the binary directory.

        Returns: str: The version of the PostgreSQL binary to be used for the upgrade.
        """
        from spilo_commons import get_bin_dir, get_binary_version

        try:
            spilo_configuration = yaml.safe_load(os.environ.get('SPILO_CONFIGURATION', ''))
            bin_dir = spilo_configuration.get('postgresql', {}).get('bin_dir')
        except Exception:
            bin_dir = None

        if not bin_dir and os.environ.get('PGVERSION'):
            bin_dir = get_bin_dir(os.environ['PGVERSION'])

        return get_binary_version(bin_dir)

    def check_patroni_api(self, member):
        """
        Checks the Patroni API for a given member.

        :param member: The member to check the API for.

        Returns: True if the API request was successful and returned a 200 status code, False otherwise.
        """
        try:
            response = self.request(member, timeout=2, retries=0)
            return response.status == 200
        except Exception as e:
            return logger.error('API request to %s name failed: %r', member.name, e)

    def toggle_pause(self, paused):
        """
        It's responsible for enabling or disabling maintenance mode.
        If the cluster is currently paused, this method will attempt to disable maintenance mode and 
        resume normal operation. If the cluster is not currently paused, this method will attempt to 
        enable maintenance mode and pause normal operation.        

        :param paused: A boolean value indicating whether to enable or disable maintenance mode.

        Returns: bool: True if the maintenance mode was successfully enabled or disabled, False otherwise.
        """
        from patroni.config import get_global_config
        from patroni.utils import polling_loop

        cluster = self.dcs.get_cluster()
        config = cluster.config.data.copy()
        if get_global_config(cluster).is_paused == paused:
            return logger.error('Cluster is %spaused, can not continue', ('' if paused else 'not '))

        config['pause'] = paused
        if not self.dcs.set_config_value(json.dumps(config, separators=(',', ':')), cluster.config.version):
            return logger.error('Failed to pause cluster, can not continue')

        self.paused = paused

        old = {m.name: m.index for m in cluster.members if m.api_url}
        ttl = config.get('ttl', self.dcs.ttl)
        for _ in polling_loop(ttl + 1):
            cluster = self.dcs.get_cluster()
            if all(m.data.get('pause', False) == paused for m in cluster.members if m.name in old):
                logger.info('Maintenance mode %s', ('enabled' if paused else 'disabled'))
                return True

        remaining = [m.name for m in cluster.members if m.data.get('pause', False) != paused
                     and m.name in old and old[m.name] != m.index]
        if remaining:
            return logger.error("%s members didn't recognized pause state after %s seconds", remaining, ttl)

    def resume_cluster(self):
        """
        Resumes the cluster by disabling maintenance mode.
        If the cluster is currently paused, this method will attempt to disable
        maintenance mode and resume normal operation.

        Raises: Exception: If an error occurs while resuming the cluster.
        """
        if self.paused:
            try:
                logger.info('Disabling maintenance mode')
                self.toggle_pause(False)
            except Exception as e:
                logger.error('Failed to resume cluster: %r', e)

    def ensure_replicas_state(self, cluster):
        """
        This method checks the satatus of all replicas and also tries to open connections
        to all of them and puts into the `self.replica_connections` dict for a future usage.
        
        :param cluster: cluster object representing the PostgreSQL cluster.
        
        Returns: bool: True if all replicas are streaming from the primary and are healthy, False otherwise.
        """
        self.replica_connections = {}
        streaming = {a: l for a, l in self.postgresql.query(
            ("SELECT client_addr, pg_catalog.pg_{0}_{1}_diff(pg_catalog.pg_current_{0}_{1}(),"
             " COALESCE(replay_{1}, '0/0'))::bigint FROM pg_catalog.pg_stat_replication")
            .format(self.postgresql.wal_name, self.postgresql.lsn_name))}

        def ensure_replica_state(member):
            """
            Checks the state of a sinble replica and opens a connection to it.
            checks if the replication lag on the replica is too high (more than 16 MB). 
            If the replica is streaming from the primary and is healthy, it opens a connection to it and
            puts it into the `self.replica_connections` dictionary for a future usage.
            
            :param member: A member object representing the replica.

            Returns: bool: True if the replica is streaming from the primary and is healthy, False otherwise.
            """
            ip = member.conn_kwargs().get('host')
            lag = streaming.get(ip)
            if lag is None:
                return logger.error('Member %s is not streaming from the primary', member.name)
            if lag > 16*1024*1024:
                return logger.error('Replication lag %s on member %s is too high', lag, member.name)

            if not self.check_patroni_api(member):
                return logger.error('Patroni on %s is not healthy', member.name)

            conn_kwargs = member.conn_kwargs(self.postgresql.config.superuser)
            conn_kwargs['options'] = '-c statement_timeout=0 -c search_path='
            conn_kwargs.pop('connect_timeout', None)

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
        """
        Perform sanity checks before triggering an upgrade.

        :param cluster: cluster object representing the PostgreSQL cluster.

        Raises: Exception: If any of the sanity checks fail.
        """
        from patroni.config import get_global_config

        if not cluster.initialize:
            return logger.error('Upgrade can not be triggered because the cluster is not initialized')

        if len(cluster.members) != self.replica_count:
            return logger.error('Upgrade can not be triggered because the number of replicas does not match (%s != %s)',
                                len(cluster.members), self.replica_count)
        if get_global_config(cluster).is_paused:
            return logger.error('Upgrade can not be triggered because Patroni is in maintenance mode')

        lock_owner = cluster.leader and cluster.leader.name
        if lock_owner != self.postgresql.name:
            return logger.error('Upgrade can not be triggered because the current node does not own the leader lock')

        return self.ensure_replicas_state(cluster)

    def remove_initialize_key(self):
        """
        Removes the initialize key from the cluster.
        This method checks if the cluster has an initialize key set, and if so, attempts to remove it by canceling the
        initialization process. It uses a polling loop to check the cluster's state multiple times before giving up.

        Returns: bool: True if the initialize key was successfully removed, False otherwise.
        """
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
        """
        Ensure that all replica nodes of a PostgreSQL database have caught up with the primary node to a specific
        Log Sequence Number (LSN).
        Importing the polling_loop function from the patroni.utils module. This function is used to create a 
        loop that polls for a certain condition.

        :param checkpoint_lsn: Sequence Number (LSN) up to which the replica nodes need to catch up

        Returns: bool: True if all replicas have caught up to the checkpoint_lsn. False otherwise.
        """
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
        """
        It is responsible for creating configuration files for rsyncd, a daemon for rsync, which is a tool used 
        for copying and synchronizing files across systems.
        
        :param rsyncd_configs_created: A boolean attribute set to True indicating that the rsyncd configurations have been created.
        :param rsyncd_conf_dir: A string representing the directory for the rsyncd configuration files (/run/rsync).
        :param rsyncd_feedback_dir: A string representing a subdirectory for feedback (/run/rsync/feedback).
        :param rsyncd_conf: A string representing the path for the main rsyncd configuration file (rsyncd.conf).
        :param secrets_file: A string representing the path for the secrets file (rsyncd.secrets), which is located in the rsyncd configuration directory.
        :param auth_users: A string representing a comma-separated list of all the keys in the replica_connections dictionary.
        :param replica_ips: A string representing a comma-separated list of the first element of all the values in the replica_connections dictionary.
        """
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
            f.write("""port = {0}
use chroot = false

[pgroot]
path = {1}
read only = true
timeout = 300
post-xfer exec = echo $RSYNC_EXIT_STATUS > {2}/$RSYNC_USER_NAME
auth users = {3}
secrets file = {4}
hosts allow = {5}
hosts deny = *
""".format(RSYNC_PORT, os.path.dirname(self.postgresql.data_dir),
                self.rsyncd_feedback_dir, auth_users, secrets_file, replica_ips))

        with open(secrets_file, 'w') as f:
            for name in self.replica_connections.keys():
                f.write('{0}:{1}\n'.format(name, self.postgresql.config.replication['password']))
        os.chmod(secrets_file, 0o600)

    def start_rsyncd(self):
        """
        Starts the rsync daemon for file synchronization.
        This method creates the rsync daemon configuration file and starts the rsync daemon process.
        The rsync daemon is started with the specified configuration file and runs in the foreground.
        """
        self.create_rsyncd_configs()
        self.rsyncd = subprocess.Popen(['rsync', '--daemon', '--no-detach', '--config=' + self.rsyncd_conf])
        self.rsyncd_started = True

    def stop_rsyncd(self):
        """
        Stops the rsync daemon and removes the rsync configuration directory.
        If the rsync daemon is running, it will be killed. If the rsync configuration
        directory exists, it will be removed.

        Raises: OSError: If there is an error killing the rsync daemon or removing the
                rsync configuration directory.
        """
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

    def checkpoint(self, member):
        """
        Perform a checkpoint on a specific member.
        
        :param member: A tuple containing the name and the database connection of the member.

        Returns: A tuple containing the name of the member and a boolean indicating whether the checkpoint was successful.
        """
        name, (_, cur) = member
        try:
            cur.execute('CHECKPOINT')
            return name, True
        except Exception as e:
            logger.error('CHECKPOINT on % failed: %r', name, e)
            return name, False

    def rsync_replicas(self, primary_ip):
        """
        It is responsible for synchronizing replicas using rsync, a tool used for copying and synchronizing files across systems.

        :param primary_ip: A string representing the IP address of the primary node.
        :param ret: A boolean attribute set to True indicating that the rsync was successful.
        :param status: A dictionary containing the status of the rsync operation.

        Returns: bool: True if the rsync operation was successful, False otherwise.
        """
        from patroni.utils import polling_loop

        logger.info('Notifying replicas %s to start rsync', ','.join(self.replica_connections.keys()))
        ret = True
        status = {}
        for name, (ip, cur) in self.replica_connections.items():
            try:
                cur.execute("SELECT pg_catalog.pg_backend_pid()")
                pid = cur.fetchone()[0]
                # We use the COPY TO PROGRAM "hack" to start the rsync on replicas.
                # There are a few important moments:
                # 1. The script is started as a child process of postgres backend, which
                #    is running with the clean environment. I.e., the script will not see
                #    values of PGVERSION, SPILO_CONFIGURATION, KUBERNETES_SERVICE_HOST
                # 2. Since access to the DCS might not be possible with pass the primary_ip
                # 3. The desired_version passed explicitly to guaranty 100% match with the master
                # 4. In order to protect from the accidental "rsync" we pass the pid of postgres backend.
                #    The script will check that it is the child of the very specific postgres process.
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

        logger.info('Waiting for replicas rsync to complete')
        status.clear()
        for _ in polling_loop(300):
            synced = True
            for name in self.replica_connections.keys():
                feedback = os.path.join(self.rsyncd_feedback_dir, name)
                if name not in status and os.path.exists(feedback):
                    with open(feedback) as f:
                        status[name] = f.read().strip()

                if name not in status:
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

    def wait_replica_restart(self, member):
        """
        Waits for the replica to restart after a major upgrade.

        :param member: The replica member object.

        Returns: str: The name of the replica member if it has restarted successfully, None otherwise.
        """
        from patroni.utils import polling_loop

        for _ in polling_loop(10):
            try:
                response = self.request(member, timeout=2, retries=0)
                if response.status == 200:
                    data = json.loads(response.data.decode('utf-8'))
                    database_system_identifier = data.get('database_system_identifier')
                    if database_system_identifier and database_system_identifier != self._old_sysid:
                        return member.name
            except Exception:
                pass
        logger.error('Patroni on replica %s was not restarted in 10 seconds', member.name)

    def wait_replicas_restart(self, cluster):
        """
        Waits for the restart of patroni on replicas.

        :param cluster: The cluster object representing the Postgres cluster.

        Returns: bool: True if all replicas successfully restarted, False otherwise.
        """
        members = [member for member in cluster.members if member.name in self.replica_connections]
        logger.info('Waiting for restart of patroni on replicas %s', ', '.join(m.name for m in members))
        pool = ThreadPool(len(members))
        results = pool.map(self.wait_replica_restart, members)
        pool.close()
        pool.join()
        logger.info('  %s successfully restarted', results)
        return all(results)

    def reset_custom_statistics_target(self):
        """
        Resets the non-default statistics target before performing analyze.
        This method retrieves the list of databases and their corresponding tables and columns
        that have a custom statistics target set. It then resets the statistics target to -1
        for each column, effectively disabling custom statistics for those columns.
        Also this method requires the `patroni.postgresql.connection` module.
        """
        from patroni.postgresql.connection import get_connection_cursor

        logger.info('Resetting non-default statistics target before analyze')
        self._statistics = defaultdict(lambda: defaultdict(dict))

        conn_kwargs = self.postgresql.local_conn_kwargs

        for d in self.postgresql.query('SELECT datname FROM pg_catalog.pg_database WHERE datallowconn'):
            conn_kwargs['dbname'] = d[0]
            with get_connection_cursor(**conn_kwargs) as cur:
                cur.execute('SELECT attrelid::regclass, quote_ident(attname), attstattarget '
                            'FROM pg_catalog.pg_attribute WHERE attnum > 0 AND NOT attisdropped AND attstattarget > 0')
                for table, column, target in cur.fetchall():
                    query = 'ALTER TABLE {0} ALTER COLUMN {1} SET STATISTICS -1'.format(table, column)
                    logger.info("Executing '%s' in the database=%s. Old value=%s", query, d[0], target)
                    cur.execute(query)
                    self._statistics[d[0]][table][column] = target

    def restore_custom_statistics_target(self):
        """
        Restores the default statistics targets after an upgrade.
        This method connects to each database specified in the `_statistics` attribute and executes
        an ALTER TABLE statement for each table and column specified in the `_statistics` attribute.
        The ALTER TABLE statement sets the statistics target for the column to the value specified.
        """
        from patroni.postgresql.connection import get_connection_cursor

        if not self._statistics:
            return

        conn_kwargs = self.postgresql.local_conn_kwargs

        logger.info('Restoring default statistics targets after upgrade')
        for db, val in self._statistics.items():
            conn_kwargs['dbname'] = db
            with get_connection_cursor(**conn_kwargs) as cur:
                for table, val in val.items():
                    for column, target in val.items():
                        query = 'ALTER TABLE {0} ALTER COLUMN {1} SET STATISTICS {2}'.format(table, column, target)
                        logger.info("Executing '%s' in the database=%s", query, db)
                        try:
                            cur.execute(query)
                        except Exception:
                            logger.error("Failed to execute '%s'", query)

    def reanalyze(self):
        """
        Reanalyzes the tables in the PostgreSQL database using the ANALYZE command.
        This method iterates over the statistics stored in the `_statistics` attribute and executes the ANALYZE command
        for each table in each database. It uses the `get_connection_cursor` function from the `patroni.postgresql.connection`
        module to establish a connection to the local PostgreSQL instance.

        Raises: Exception: If there is an error executing the ANALYZE command for any table.
        """
        from patroni.postgresql.connection import get_connection_cursor

        if not self._statistics:
            return

        conn_kwargs = self.postgresql.local_conn_kwargs

        for db, val in self._statistics.items():
            conn_kwargs['dbname'] = db
            with get_connection_cursor(**conn_kwargs) as cur:
                for table in val.keys():
                    query = 'ANALYZE {0}'.format(table)
                    logger.info("Executing '%s' in the database=%s", query, db)
                    try:
                        cur.execute(query)
                    except Exception:
                        logger.error("Failed to execute '%s'", query)

    def analyze(self):
        """
        Analyzes the database by resetting and restoring custom statistics targets.
        This method first resets the custom statistics targets, then performs a database analysis,
        and finally restores the custom statistics targets. If any error occurs during the process,
        it logs the error message.

        Raises: Exception: If an error occurs during the reset or restore of custom statistics targets.
        """
        try:
            self.reset_custom_statistics_target()
        except Exception as e:
            logger.error('Failed to reset custom statistics targets: %r', e)
        self.postgresql.analyze(True)
        try:
            self.restore_custom_statistics_target()
        except Exception as e:
            logger.error('Failed to restore custom statistics targets: %r', e)

    def do_upgrade(self):
        """
        This method is responsible for upgrading a PostgreSQL database cluster.
        It performs the following steps, checks if the upgrade, checks if the PostgreSQL instance is running and there is a leader,
        checks if the cluster is ready to be upgraded, prepares the new PGDATA directory, drops possibly incompatible extensions,
        run a pg_upgrade check, drops possibly incompatible objects, enable maintenance mode, stops the PostgreSQL instance,
        starts rsyncd, waits for replicas to catch up, run a CHECKPOINT on replicas, execute the pg_upgrade, switches PGDATA directories,
        removes the initialize key, kills Patroni, waits for Patroni to restart, starts the PostgreSQL instance,
        updates the configuration files, performs a CHECKPOINT on replicas, rsyncs replicas, wait for replicas to restart, 
        run a database analyze, updates the extensions, run a post-upgrade cleanup, run a backup and execute a post-cleanup.
        
        Returns: bool: True if the upgrade was successful, False otherwise.        
        """
        from patroni.utils import polling_loop

        if not self.upgrade_required:
            logger.info('Current version=%s, desired version=%s. Upgrade is not required',
                        self.cluster_version, self.desired_version)
            return True

        if not (self.postgresql.is_running() and self.postgresql.is_leader()):
            return logger.error('PostgreSQL is not running or in recovery')

        cluster = self.dcs.get_cluster()

        if not self.sanity_checks(cluster):
            return False

        self._old_sysid = self.postgresql.sysid  # remember old sysid

        logger.info('Cluster %s is ready to be upgraded', self.postgresql.scope)
        if not self.postgresql.prepare_new_pgdata(self.desired_version):
            return logger.error('initdb failed')

        try:
            self.postgresql.drop_possibly_incompatible_extensions()
        except Exception:
            return logger.error('Failed to drop possibly incompatible extensions')

        if not self.postgresql.pg_upgrade(check=True):
            return logger.error('pg_upgrade --check failed, more details in the %s_upgrade', self.postgresql.data_dir)

        try:
            self.postgresql.drop_possibly_incompatible_objects()
        except Exception:
            return logger.error('Failed to drop possibly incompatible objects')

        logging.info('Enabling maintenance mode')
        if not self.toggle_pause(True):
            return False

        logger.info('Doing a clean shutdown of the cluster before pg_upgrade')
        downtime_start = time.time()
        if not self.postgresql.stop(block_callbacks=True):
            return logger.error('Failed to stop the cluster before pg_upgrade')

        if self.replica_connections:
            from patroni.postgresql.misc import parse_lsn

            # Make sure we use the pg_controldata from the correct major version
            self.postgresql.set_bin_dir(self.cluster_version)
            controldata = self.postgresql.controldata()
            self.postgresql.set_bin_dir(self.desired_version)

            checkpoint_lsn = controldata.get('Latest checkpoint location')
            if controldata.get('Database cluster state') != 'shut down' or not checkpoint_lsn:
                return logger.error("Cluster wasn't shut down cleanly")

            checkpoint_lsn = parse_lsn(checkpoint_lsn)
            logger.info('Latest checkpoint location: %s', checkpoint_lsn)

            logger.info('Starting rsyncd')
            self.start_rsyncd()

            if not self.wait_for_replicas(checkpoint_lsn):
                return False

            if not (self.rsyncd.pid and self.rsyncd.poll() is None):
                return logger.error('Failed to start rsyncd')

        if self.replica_connections:
            logger.info('Executing CHECKPOINT on replicas %s', ','.join(self.replica_connections.keys()))
            pool = ThreadPool(len(self.replica_connections))
            # Do CHECKPOINT on replicas in parallel with pg_upgrade.
            # It will reduce the time for shutdown and so downtime.
            results = pool.map_async(self.checkpoint, self.replica_connections.items())
            pool.close()

        if not self.postgresql.pg_upgrade():
            return logger.error('Failed to upgrade cluster from %s to %s', self.cluster_version, self.desired_version)

        self.postgresql.switch_pgdata()
        self.upgrade_complete = True

        logger.info('Updating configuration files')
        envdir = update_configs(self.desired_version)

        ret = True
        if self.replica_connections:
            # Check status of replicas CHECKPOINT and remove connections that are failed.
            pool.join()
            if results.ready():
                for name, status in results.get():
                    if not status:
                        ret = False
                        self.replica_connections.pop(name)

        member = cluster.get_member(self.postgresql.name)
        if self.replica_connections:
            primary_ip = member.conn_kwargs().get('host')
            rsync_start = time.time()
            try:
                if not self.rsync_replicas(primary_ip):
                    ret = False
            except Exception as e:
                logger.error('rsync failed: %r', e)
                ret = False
            logger.info('Rsync took %s seconds', time.time() - rsync_start)

            self.stop_rsyncd()
            time.sleep(2)  # Give replicas a bit of time to switch PGDATA

        self.remove_initialize_key()
        kill_patroni()
        self.remove_initialize_key()

        time.sleep(1)
        for _ in polling_loop(10):
            if self.check_patroni_api(member):
                break
        else:
            logger.error('Patroni REST API on primary is not accessible after 10 seconds')

        logger.info('Starting the primary postgres up')
        for _ in polling_loop(10):
            try:
                result = self.request(member, 'post', 'restart', {})
                logger.info('   %s %s', result.status, result.data.decode('utf-8'))
                if result.status < 300:
                    break
            except Exception as e:
                logger.error('POST /restart failed: %r', e)
        else:
            logger.error('Failed to start primary after upgrade')

        logger.info('Upgrade downtime: %s', time.time() - downtime_start)

        # The last attempt to fix initialize key race condition
        cluster = self.dcs.get_cluster()
        if cluster.initialize == self._old_sysid:
            self.dcs.cancel_initialization()

        try:
            self.postgresql.update_extensions()
        except Exception as e:
            logger.error('Failed to update extensions: %r', e)

        # start analyze early
        analyze_thread = Thread(target=self.analyze)
        analyze_thread.start()

        if self.replica_connections:
            self.wait_replicas_restart(cluster)

        self.resume_cluster()

        analyze_thread.join()

        self.reanalyze()

        logger.info('Total upgrade time (with analyze): %s', time.time() - downtime_start)
        self.postgresql.bootstrap.call_post_bootstrap(self.config['bootstrap'])
        self.postgresql.cleanup_old_pgdata()

        if envdir:
            self.start_backup(envdir)

        return ret

    def post_cleanup(self):
        """
        Performs post-cleanup tasks after the upgrade process.
        This method stops the rsync daemon, resumes the cluster, and cleans up the new PGDATA directory if it was created.
        """
        self.stop_rsyncd()
        self.resume_cluster()

        if self.new_data_created:
            try:
                self.postgresql.cleanup_new_pgdata()
            except Exception as e:
                logger.error('Failed to remove new PGDATA %r', e)

    def try_upgrade(self, replica_count):
        """
        Tries to perform the upgrade by setting the replica count and calling the do_upgrade method.
        Finally, it performs post-cleanup operations.
            
        :param  replica_count: The number of replicas to set before performing the upgrade.
            
        Returns: The result of the do_upgrade method.
        """
        try:
            self.replica_count = replica_count
            return self.do_upgrade()
        finally:
            self.post_cleanup()

    def start_backup(self, envdir):
        """
        Initiates a new backup by calling the postgres_backup.sh script with the specified environment directory and data directory.

        :param  envdir: The path string to the environment directory.
        """
        logger.info('Initiating a new backup...')
        if not os.fork():
            subprocess.call(['nohup', 'envdir', envdir, '/scripts/postgres_backup.sh', self.postgresql.data_dir],
                            stdout=open(os.devnull, 'w'), stderr=subprocess.STDOUT)


# this function will be running in a clean environment, therefore we can't rely on DCS connection
def rsync_replica(config, desired_version, primary_ip, pid):
    """
    It is responsible for synch of the replica and primary during the upgrade process.
    It imports the PostgresqlUpgrade class from the pg_upgrade module and the polling_loop function from the patroni.utils module.
    Check if the PostgreSQL version in replica matches the desired version, stops PostgreSQL instance and switches the PGDATA directory.
    Update the configuration files and restarts Patroni, remove the recovery.conf file and restarts Patroni again.
    Returns the result of the cleanup_old_pgdata method.
        
    :param config: A Config object representing the Patroni configuration.
    :param desired_version: A string representing the desired version of the PostgreSQL binary to be used for the upgrade.
    :param primary_ip: A string representing the IP address of the primary node.
    :param pid: An integer representing the process ID of the PostgreSQL backend process.    

    Returns: int: 0 if the rsync was successful, 1 otherwise.
    """
    from pg_upgrade import PostgresqlUpgrade
    from patroni.utils import polling_loop

    me = psutil.Process()

    # check that we are the child of postgres backend
    if me.parent().pid != pid and me.parent().parent().pid != pid:
        return 1

    backend = psutil.Process(pid)
    if 'postgres' not in backend.name():
        return 1

    postgresql = PostgresqlUpgrade(config)

    if postgresql.get_cluster_version() == desired_version:
        return 0

    if os.fork():
        return 0

    # Wait until the remote side will close the connection and backend process exits
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
    if subprocess.call(['rsync', '--archive', '--delete', '--hard-links', '--size-only', '--omit-dir-times',
                        '--no-inc-recursive', '--include=/data/***', '--include=/data_old/***',
                        '--exclude=/data/pg_xlog/*', '--exclude=/data_old/pg_xlog/*',
                        '--exclude=/data/pg_wal/*', '--exclude=/data_old/pg_wal/*', '--exclude=*',
                        'rsync://{0}@{1}:{2}/pgroot'.format(postgresql.name, primary_ip, RSYNC_PORT),
                        os.path.dirname(postgresql.data_dir)], env=env) != 0:
        logger.error('Failed to rsync from %s', primary_ip)
        postgresql.switch_back_pgdata()
        # XXX: rollback configs?
        return 1

    conn_kwargs = {k: v for k, v in postgresql.config.replication.items() if v is not None}
    if 'username' in conn_kwargs:
        conn_kwargs['user'] = conn_kwargs.pop('username')

    # If restart Patroni right now there is a chance that it will exit due to the sysid mismatch.
    # Due to cleaned environment we can't always use DCS on replicas in this script, therefore
    # the good indicator of initialize key being deleted/updated is running primary after the upgrade.
    for _ in polling_loop(300):
        try:
            with postgresql.get_replication_connection_cursor(primary_ip, **conn_kwargs) as cur:
                cur.execute('IDENTIFY_SYSTEM')
                if cur.fetchone()[0] != sysid:
                    break
        except Exception:
            pass

    # If the cluster was unpaused earlier than we restarted Patroni, it might have created
    # the recovery.conf file and tried (and failed) to start the cluster up using wrong binaries.
    # In case of upgrade to 12+ presence of PGDATA/recovery.conf will not allow postgres to start.
    # We remove the recovery.conf and restart Patroni in order to make sure it is using correct config.
    try:
        postgresql.config.remove_recovery_conf()
    except Exception:
        pass
    kill_patroni()
    try:
        postgresql.config.remove_recovery_conf()
    except Exception:
        pass

    return postgresql.cleanup_old_pgdata()


def main():
    """
    Starting point of the script.
    Parses command line arguments and performs either an rsync_replica operation or an inplace upgrade.
    Returns:
        0 if the operation is successful,
        1 if the operation fails,
        2 if the command line arguments are invalid.
    """
    from patroni.config import Config
    from spilo_commons import PATRONI_CONFIG_FILE

    config = Config(PATRONI_CONFIG_FILE)

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
    logging.basicConfig(format='%(asctime)s inplace_upgrade %(levelname)s: %(message)s', level='INFO')
    sys.exit(main())
