import logging
import os
import shutil
import subprocess
import re
import psutil

from patroni.postgresql import Postgresql

logger = logging.getLogger(__name__)


class PostgresqlUpgrade(Postgresql):

    def adjust_shared_preload_libraries(self, version):
        shared_preload_libraries = self.config['parameters'].get('shared_preload_libraries')
        self._old_config_values['shared_preload_libraries'] = shared_preload_libraries

        extensions = {
            'timescaledb':    (9.6, 11),
            'pg_cron':        (9.5, 11),
            'pg_stat_kcache': (9.4, 11),
            'pg_partman':     (9.4, 11),
            'set_user':       (9.4, 11)
        }

        filtered = []
        for value in shared_preload_libraries.split(','):
            value = value.strip()
            if value not in extensions or version >= extensions[value][0] and version <= extensions[value][1]:
                filtered.append(value)
        self.config['parameters']['shared_preload_libraries'] = ','.join(filtered)

    def start_old_cluster(self, config, version):
        self.set_bin_dir(version)

        version = float(version)

        config[config['method']]['command'] = 'true'
        if version < 9.5:  # 9.4 and older don't have recovery_target_action
            action = config[config['method']].get('recovery_target_action')
            config[config['method']]['pause_at_recovery_target'] = str(action == 'pause').lower()

        # make sure we don't archive wals from the old version
        self._old_config_values = {'archive_mode': self.config['parameters'].get('archive_mode')}
        self.config['parameters']['archive_mode'] = 'off'

        # and don't load shared_preload_libraries which don't exist in the old version
        self.adjust_shared_preload_libraries(version)

        # make sure we don't execute callbacks before cluster is upgraded
        self.config['callbacks'] = {}

        return self.bootstrap(config)

    def get_binary_version(self):
        version = subprocess.check_output([self._pgcommand('postgres'), '--version']).decode()
        version = re.match('^[^\s]+ [^\s]+ (\d+)\.(\d+)', version)
        return '.'.join(version.groups()) if int(version.group(1)) < 10 else version.group(1)

    def get_cluster_version(self):
        with open(self._version_file) as f:
            return f.read().strip()

    def set_bin_dir(self, version):
        self._old_bin_dir = self._bin_dir
        self._bin_dir = '/usr/lib/postgresql/{0}/bin'.format(version)

    def copy_configs(self):
        for f in os.listdir(self._old_data_dir):
            if f.startswith('postgresql.') or f.startswith('pg_hba.conf') or f == 'patroni.dynamic.json':
                shutil.copy(os.path.join(self._old_data_dir, f), os.path.join(self._data_dir, f))
        return True

    def restore_parameters(self):
        # restore original values of archive_mode and shared_preload_libraries
        for name, value in self._old_config_values.items():
            if value is None:
                self._server_parameters.pop(name)
            else:
                self._server_parameters[name] = value
        self._write_postgresql_conf()
        return True

    def drop_possibly_incompatible_objects(self):
        conn_kwargs = self._local_connect_kwargs
        for p in ['connect_timeout', 'options']:
            conn_kwargs.pop(p, None)

        for d in self.query('SELECT datname FROM pg_catalog.pg_database WHERE datallowconn'):
            conn_kwargs['database'] = d[0]
            with self._get_connection_cursor(**conn_kwargs) as cur:
                cur.execute("SET synchronous_commit = 'local'")
                logger.info('Executing "DROP SCHEMA IF EXISTS metric_helpers" in the database="%s"', d[0])
                cur.execute("DROP FUNCTION metric_helpers.pg_stat_statements(boolean) CASCADE")
                logger.info('Executing "DROP EXTENSION IF EXISTS amcheck_next" in the database="%s"', d[0])
                cur.execute("DROP EXTENSION IF EXISTS amcheck_next")

    def pg_upgrade(self):
        self._upgrade_dir = self._data_dir + '_upgrade'
        if os.path.exists(self._upgrade_dir) and os.path.isdir(self._upgrade_dir):
            shutil.rmtree(self._upgrade_dir)

        os.makedirs(self._upgrade_dir)
        self._old_cwd = os.getcwd()
        os.chdir(self._upgrade_dir)

        pg_upgrade_args = ['-k', '-j', str(psutil.cpu_count()),
                           '-b', self._old_bin_dir, '-B', self._bin_dir,
                           '-d', self._old_data_dir, '-D', self._data_dir,
                           '-O', "-c timescaledb.restoring='on'"]
        if 'username' in self._superuser:
            pg_upgrade_args += ['-U', self._superuser['username']]

        return subprocess.call([self._pgcommand('pg_upgrade')] + pg_upgrade_args) == 0

    def do_upgrade(self, version, initdb_config):
        self._data_dir = os.path.abspath(self._data_dir)
        self._old_data_dir = self._data_dir + '_old'
        os.rename(self._data_dir, self._old_data_dir)

        self.set_bin_dir(version)

        if self._initdb(initdb_config) and self.copy_configs() and self.restore_parameters() and self.pg_upgrade():
            os.chdir(self._old_cwd)
            shutil.rmtree(self._upgrade_dir)
            shutil.rmtree(self._old_data_dir)
            return True

    def analyze(self):
        vacuumdb_args = ['-a', '-Z', '-j', str(psutil.cpu_count())]
        if 'username' in self._superuser:
            vacuumdb_args += ['-U', self._superuser['username']]
        subprocess.call([self._pgcommand('vacuumdb')] + vacuumdb_args)
