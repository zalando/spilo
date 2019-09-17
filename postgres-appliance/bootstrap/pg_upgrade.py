import logging
import os
import shutil
import subprocess
import re
import psutil

from patroni.postgresql import Postgresql
from patroni.postgresql.connection import get_connection_cursor

logger = logging.getLogger(__name__)


class PostgresqlUpgrade(Postgresql):

    def adjust_shared_preload_libraries(self, version):
        shared_preload_libraries = self.config.get('parameters').get('shared_preload_libraries')
        self._old_config_values['shared_preload_libraries'] = shared_preload_libraries

        extensions = {
            'timescaledb':    (9.6, 11),
            'pg_cron':        (9.5, 12),
            'pg_stat_kcache': (9.4, 12),
            'pg_partman':     (9.4, 12)
        }

        filtered = []
        for value in shared_preload_libraries.split(','):
            value = value.strip()
            if value not in extensions or version >= extensions[value][0] and version <= extensions[value][1]:
                filtered.append(value)
        self.config.get('parameters')['shared_preload_libraries'] = ','.join(filtered)

    def start_old_cluster(self, config, version):
        self.set_bin_dir(version)

        version = float(version)

        config[config['method']]['command'] = 'true'
        if version < 9.5:  # 9.4 and older don't have recovery_target_action
            action = config[config['method']].get('recovery_target_action')
            config[config['method']]['pause_at_recovery_target'] = str(action == 'pause').lower()

        # make sure we don't archive wals from the old version
        self._old_config_values = {'archive_mode': self.config.get('parameters').get('archive_mode')}
        self.config.get('parameters')['archive_mode'] = 'off'

        # and don't load shared_preload_libraries which don't exist in the old version
        self.adjust_shared_preload_libraries(version)

        return self.bootstrap.bootstrap(config)

    def get_binary_version(self):
        version = subprocess.check_output([self.pgcommand('postgres'), '--version']).decode()
        version = re.match('^[^\s]+ [^\s]+ (\d+)(\.(\d+))?', version)
        return '.'.join([version.group(1), version.group(3)]) if int(version.group(1)) < 10 else version.group(1)

    def get_cluster_version(self):
        with open(self._version_file) as f:
            return f.read().strip()

    def set_bin_dir(self, version):
        self._old_bin_dir = self._bin_dir
        self._bin_dir = '/usr/lib/postgresql/{0}/bin'.format(version)

    def drop_possibly_incompatible_objects(self):
        conn_kwargs = self.config.local_connect_kwargs
        for p in ['connect_timeout', 'options']:
            conn_kwargs.pop(p, None)

        for d in self.query('SELECT datname FROM pg_catalog.pg_database WHERE datallowconn'):
            conn_kwargs['database'] = d[0]
            with get_connection_cursor(**conn_kwargs) as cur:
                cur.execute("SET synchronous_commit = 'local'")
                logger.info('Executing "DROP FUNCTION metric_helpers.pg_stat_statements" in the database="%s"', d[0])
                cur.execute("DROP FUNCTION metric_helpers.pg_stat_statements(boolean) CASCADE")
                logger.info('Executing "DROP EXTENSION IF EXISTS amcheck_next" in the database="%s"', d[0])
                cur.execute("DROP EXTENSION IF EXISTS amcheck_next")

    def pg_upgrade(self):
        upgrade_dir = self._data_dir + '_upgrade'
        if os.path.exists(upgrade_dir) and os.path.isdir(upgrade_dir):
            shutil.rmtree(upgrade_dir)

        os.makedirs(upgrade_dir)

        old_cwd = os.getcwd()
        os.chdir(upgrade_dir)

        pg_upgrade_args = ['-k', '-j', str(psutil.cpu_count()),
                           '-b', self._old_bin_dir, '-B', self._bin_dir,
                           '-d', self._old_data_dir, '-D', self._data_dir,
                           '-O', "-c timescaledb.restoring='on'"]
        if 'username' in self.config.superuser:
            pg_upgrade_args += ['-U', self.config.superuser['username']]

        if subprocess.call([self.pgcommand('pg_upgrade')] + pg_upgrade_args) == 0:
            os.chdir(old_cwd)
            shutil.rmtree(upgrade_dir)
            shutil.rmtree(self._old_data_dir)
            return True

    def do_upgrade(self, version, initdb_config):
        self._data_dir = os.path.abspath(self._data_dir)
        self._old_data_dir = self._data_dir + '_old'
        os.rename(self._data_dir, self._old_data_dir)

        self.set_bin_dir(version)

        # restore original values of archive_mode and shared_preload_libraries
        for name, value in self._old_config_values.items():
            if value is None:
                self.config.get('parameters').pop(name)
            else:
                self.config.get('parameters')[name] = value

        if not self.bootstrap._initdb(initdb_config):
            return False

        # Copy old configs. XXX: some parameters might be incompatible!
        for f in os.listdir(self._old_data_dir):
            if f.startswith('postgresql.') or f.startswith('pg_hba.conf') or f == 'patroni.dynamic.json':
                shutil.copy(os.path.join(self._old_data_dir, f), os.path.join(self._data_dir, f))

        self.config.write_postgresql_conf()

        return self.pg_upgrade()

    def analyze(self):
        vacuumdb_args = ['-a', '-Z', '-j', str(psutil.cpu_count())]
        if 'username' in self.config.superuser:
            vacuumdb_args += ['-U', self.config.superuser['username']]
        subprocess.call([self.pgcommand('vacuumdb')] + vacuumdb_args)
