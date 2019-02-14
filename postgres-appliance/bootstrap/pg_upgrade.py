import logging
import os
import shutil
import subprocess
import re
import psutil

from patroni.postgresql import Postgresql

logger = logging.getLogger(__name__)


class PostgresqlUpgrade(Postgresql):

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

    def drop_possibly_incompatible_objects(self):
        conn_kwargs = self._local_connect_kwargs
        for p in ['connect_timeout', 'options']:
            conn_kwargs.pop(p, None)

        for d in self.query('SELECT datname FROM pg_catalog.pg_database WHERE datallowconn'):
            logger.info('Executing "DROP SCHEMA IF EXISTS metric_helpers" in the database="%s"', d[0])
            conn_kwargs['database'] = d[0]
            with self._get_connection_cursor(**conn_kwargs) as cur:
                cur.execute("SET synchronous_commit = 'local'")
                cur.execute("DROP SCHEMA IF EXISTS metric_helpers CASCADE")

    def pg_upgrade(self):
        self._upgrade_dir = self._data_dir + '_upgrade'
        if os.path.exists(self._upgrade_dir) and os.path.isdir(self._upgrade_dir):
            shutil.rmtree(self._upgrade_dir)

        os.makedirs(self._upgrade_dir)
        self._old_cwd = os.getcwd()
        os.chdir(self._upgrade_dir)

        pg_upgrade_args = ['-k', '-j', str(psutil.cpu_count()),
                           '-b', self._old_bin_dir, '-B', self._bin_dir,
                           '-d', self._old_data_dir, '-D', self._data_dir]
        if 'username' in self._superuser:
            pg_upgrade_args += ['-U', self._superuser['username']]

        return subprocess.call([self._pgcommand('pg_upgrade')] + pg_upgrade_args) == 0

    def do_upgrade(self, version, initdb_config):
        self._data_dir = os.path.abspath(self._data_dir)
        self._old_data_dir = self._data_dir + '_old'
        os.rename(self._data_dir, self._old_data_dir)

        self.set_bin_dir(version)

        if self._initdb(initdb_config) and self.copy_configs() and self.pg_upgrade():
            os.chdir(self._old_cwd)
            shutil.rmtree(self._upgrade_dir)
            shutil.rmtree(self._old_data_dir)
            return True

    def analyze(self):
        vacuumdb_args = ['-a', '-Z', '-j', str(psutil.cpu_count())]
        if 'username' in self._superuser:
            vacuumdb_args += ['-U', self._superuser['username']]
        subprocess.call([self._pgcommand('vacuumdb')] + vacuumdb_args)
