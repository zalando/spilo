import logging
import os
import shutil
import subprocess
import psutil

from patroni.postgresql import Postgresql

logger = logging.getLogger(__name__)


class _PostgresqlUpgrade(Postgresql):

    def adjust_shared_preload_libraries(self, version):
        from spilo_commons import adjust_extensions

        shared_preload_libraries = self.config.get('parameters').get('shared_preload_libraries')
        self._old_config_values['shared_preload_libraries'] = shared_preload_libraries

        if shared_preload_libraries:
            self.config.get('parameters')['shared_preload_libraries'] =\
                    adjust_extensions(shared_preload_libraries, version)

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

    def get_cluster_version(self):
        with open(self._version_file) as f:
            return f.read().strip()

    def set_bin_dir(self, version):
        from spilo_commons import get_bin_dir

        self._old_bin_dir = self._bin_dir
        self._bin_dir = get_bin_dir(version)

    @property
    def local_conn_kwargs(self):
        conn_kwargs = self.config.local_connect_kwargs
        conn_kwargs['options'] = '-c synchronous_commit=local -c statement_timeout=0 -c search_path='
        conn_kwargs.pop('connect_timeout', None)
        return conn_kwargs

    def drop_possibly_incompatible_objects(self):
        from patroni.postgresql.connection import get_connection_cursor

        logger.info('Dropping objects from the cluster which could be incompatible')
        conn_kwargs = self.local_conn_kwargs

        for d in self.query('SELECT datname FROM pg_catalog.pg_database WHERE datallowconn'):
            conn_kwargs['database'] = d[0]
            with get_connection_cursor(**conn_kwargs) as cur:
                logger.info('Executing "DROP FUNCTION metric_helpers.pg_stat_statements" in the database="%s"', d[0])
                cur.execute("DROP FUNCTION IF EXISTS metric_helpers.pg_stat_statements(boolean) CASCADE")
                logger.info('Executing "DROP EXTENSION pg_stat_kcache"')
                cur.execute("DROP EXTENSION IF EXISTS pg_stat_kcache")
                logger.info('Executing "DROP EXTENSION pg_stat_statements"')
                cur.execute("DROP EXTENSION IF EXISTS pg_stat_statements")
                logger.info('Executing "DROP EXTENSION IF EXISTS amcheck_next" in the database="%s"', d[0])
                cur.execute("DROP EXTENSION IF EXISTS amcheck_next")
                if d[0] == 'postgres':
                    logger.info('Executing "DROP TABLE postgres_log CASCADE" in the database=postgres')
                    cur.execute('DROP TABLE IF EXISTS public.postgres_log CASCADE')
                cur.execute("SELECT oid::regclass FROM pg_catalog.pg_class WHERE relpersistence = 'u'")
                for unlogged in cur.fetchall():
                    logger.info('Truncating unlogged table %s', unlogged[0])
                    try:
                        cur.execute('TRUNCATE {0}'.format(unlogged[0]))
                    except Exception as e:
                        logger.error('Failed: %r', e)

    def update_extensions(self):
        from patroni.postgresql.connection import get_connection_cursor

        conn_kwargs = self.local_conn_kwargs

        for d in self.query('SELECT datname FROM pg_catalog.pg_database WHERE datallowconn'):
            conn_kwargs['database'] = d[0]
            with get_connection_cursor(**conn_kwargs) as cur:
                cur.execute('SELECT quote_ident(extname) FROM pg_catalog.pg_extension')
                for extname in cur.fetchall():
                    query = 'ALTER EXTENSION {0} UPDATE'.format(extname[0])
                    logger.info("Executing '%s' in the database=%s", query, d[0])
                    try:
                        cur.execute(query)
                    except Exception as e:
                        logger.error('Failed: %r', e)

    @staticmethod
    def remove_new_data(d):
        if d.endswith('_new') and os.path.isdir(d):
            shutil.rmtree(d)

    def cleanup_new_pgdata(self):
        if getattr(self, '_new_data_dir', None):
            self.remove_new_data(self._new_data_dir)

    def cleanup_old_pgdata(self):
        if os.path.exists(self._old_data_dir):
            logger.info('Removing %s', self._old_data_dir)
            shutil.rmtree(self._old_data_dir)
        return True

    def switch_pgdata(self):
        self._old_data_dir = self._data_dir + '_old'
        self.cleanup_old_pgdata()
        os.rename(self._data_dir, self._old_data_dir)
        if getattr(self, '_new_data_dir', None):
            os.rename(self._new_data_dir, self._data_dir)
        self.configure_server_parameters()
        return True

    def switch_back_pgdata(self):
        if os.path.exists(self._data_dir):
            self._new_data_dir = self._data_dir + '_new'
            self.cleanup_new_pgdata()
            os.rename(self._data_dir, self._new_data_dir)
        os.rename(self._old_data_dir, self._data_dir)

    def pg_upgrade(self, check=False):
        upgrade_dir = self._data_dir + '_upgrade'
        if os.path.exists(upgrade_dir) and os.path.isdir(upgrade_dir):
            shutil.rmtree(upgrade_dir)

        os.makedirs(upgrade_dir)

        old_cwd = os.getcwd()
        os.chdir(upgrade_dir)

        pg_upgrade_args = ['-k', '-j', str(psutil.cpu_count()),
                           '-b', self._old_bin_dir, '-B', self._bin_dir,
                           '-d', self._data_dir, '-D', self._new_data_dir,
                           '-O', "-c timescaledb.restoring='on'"]
        if 'username' in self.config.superuser:
            pg_upgrade_args += ['-U', self.config.superuser['username']]

        if check:
            pg_upgrade_args += ['--check']

        logger.info('Executing pg_upgrade%s', (' --check' if check else ''))
        if subprocess.call([self.pgcommand('pg_upgrade')] + pg_upgrade_args) == 0:
            os.chdir(old_cwd)
            shutil.rmtree(upgrade_dir)
            return True

    def prepare_new_pgdata(self, version):
        from spilo_commons import append_extentions

        locale = self.query('SHOW lc_collate').fetchone()[0]
        encoding = self.query('SHOW server_encoding').fetchone()[0]
        initdb_config = [{'locale': locale}, {'encoding': encoding}]
        if self.query("SELECT current_setting('data_checksums')::bool").fetchone()[0]:
            initdb_config.append('data-checksums')

        logger.info('initdb config: %s', initdb_config)

        self._new_data_dir = os.path.abspath(self._data_dir)
        self._old_data_dir = self._new_data_dir + '_old'
        self._data_dir = self._new_data_dir + '_new'
        self.remove_new_data(self._data_dir)
        old_postgresql_conf = self.config._postgresql_conf
        self.config._postgresql_conf = os.path.join(self._data_dir, 'postgresql.conf')
        old_version_file = self._version_file
        self._version_file = os.path.join(self._data_dir, 'PG_VERSION')

        self.set_bin_dir(version)

        # restore original values of archive_mode and shared_preload_libraries
        if getattr(self, '_old_config_values', None):
            for name, value in self._old_config_values.items():
                if value is None:
                    self.config.get('parameters').pop(name)
                else:
                    self.config.get('parameters')[name] = value

        shared_preload_libraries = self.config.get('parameters').get('shared_preload_libraries')
        if shared_preload_libraries:
            self.config.get('parameters')['shared_preload_libraries'] =\
                    append_extentions(shared_preload_libraries, float(version))

        if not self.bootstrap._initdb(initdb_config):
            return False

        # Copy old configs. XXX: some parameters might be incompatible!
        for f in os.listdir(self._new_data_dir):
            if f.startswith('postgresql.') or f.startswith('pg_hba.conf') or f == 'patroni.dynamic.json':
                shutil.copy(os.path.join(self._new_data_dir, f), os.path.join(self._data_dir, f))

        self.config.write_postgresql_conf()
        self._new_data_dir, self._data_dir = self._data_dir, self._new_data_dir
        self.config._postgresql_conf = old_postgresql_conf
        self._version_file = old_version_file
        self.configure_server_parameters()
        return True

    def do_upgrade(self):
        return self.pg_upgrade() and self.switch_pgdata() and self.cleanup_old_pgdata()

    def analyze(self, in_stages=False):
        vacuumdb_args = ['--analyze-in-stages'] if in_stages else []
        logger.info('Rebuilding statistics (vacuumdb%s)', (' ' + vacuumdb_args[0] if in_stages else ''))
        vacuumdb_args += ['-a', '-Z', '-j', str(psutil.cpu_count())]
        if 'username' in self.config.superuser:
            vacuumdb_args += ['-U', self.config.superuser['username']]
        subprocess.call([self.pgcommand('vacuumdb')] + vacuumdb_args)


def PostgresqlUpgrade(config):
    config['postgresql'].update({'callbacks': {}, 'pg_ctl_timeout': 3600*24*7})

    # avoid unnecessary interactions with PGDATA and postgres
    is_running = _PostgresqlUpgrade.is_running
    _PostgresqlUpgrade.is_running = lambda s: False
    try:
        return _PostgresqlUpgrade(config['postgresql'])
    finally:
        _PostgresqlUpgrade.is_running = is_running
