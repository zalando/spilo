import logging
import os
import shutil
import subprocess
import psutil

from patroni.postgresql import Postgresql

logger = logging.getLogger(__name__)


class _PostgresqlUpgrade(Postgresql):
    """
    A class representing the PostgreSQL upgrade process.
    This class extends the `Postgresql` class and provides methods for adjusting shared_preload_libraries,
    starting the old cluster, dropping incompatible extensions and objects, updating extensions,
    cleaning up old and new pgdata directories, switching pgdata directories, performing pg_upgrade,
    preparing new pgdata, and analyzing the database.

    :ivar _old_bin_dir: The old PostgreSQL binary directory.
    :ivar _old_config_values: A dictionary of old configuration values.
    :ivar _old_data_dir: The old PostgreSQL data directory.
    :ivar _new_data_dir: The new PostgreSQL data directory.
    :ivar _version_file: The PostgreSQL version file.
    :ivar _INCOMPATIBLE_EXTENSIONS: A tuple of incompatible extensions.    
    """

    _INCOMPATIBLE_EXTENSIONS = ('amcheck_next', 'pg_repack',)

    def adjust_shared_preload_libraries(self, version):
        """
        Adjusts the shared_preload_libraries parameter based on the given version.

        :param version: The string version of PostgreSQL being upgraded to.
        """
        from spilo_commons import adjust_extensions

        shared_preload_libraries = self.config.get('parameters').get('shared_preload_libraries')
        self._old_config_values['shared_preload_libraries'] = shared_preload_libraries

        if shared_preload_libraries:
            self.config.get('parameters')['shared_preload_libraries'] =\
                    adjust_extensions(shared_preload_libraries, version)

    def no_bg_mon(self):
        """
        Remove 'bg_mon' from the 'shared_preload_libraries' configuration parameter.
        Checks if the 'shared_preload_libraries' configuration parameter is set, and if it is, 
        remove the 'bg_mon' library from the list of libraries.
        
        """
        shared_preload_libraries = self.config.get('parameters').get('shared_preload_libraries')
        if shared_preload_libraries:
            tmp = filter(lambda a: a != "bg_mon", map(lambda a: a.strip(), shared_preload_libraries.split(",")))
            self.config.get('parameters')['shared_preload_libraries'] = ",".join(tmp)

    def restore_shared_preload_libraries(self):
        """
        Restores the value of shared_preload_libraries to its original value.
        If the _old_shared_preload_libraries attribute is set, it restores the value of shared_preload_libraries
        to the stored value in the _old_shared_preload_libraries attribute.

        Returns: bool: True if the shared_preload_libraries value was successfully restored, False otherwise.
        """
        if getattr(self, '_old_shared_preload_libraries'):
            self.config.get('parameters')['shared_preload_libraries'] = self._old_shared_preload_libraries
        return True

    def start_old_cluster(self, config, version):
        """
        Starts the old cluster with the specified configuration and version.

        :param config (dict): The configuration for the old cluster.
        :param version (float): The version of the old cluster.

        Returns: bool: True if the old cluster was successfully started, False otherwise.
        """
        self.set_bin_dir(version)

        # make sure we don't archive wals from the old version
        self._old_config_values = {'archive_mode': self.config.get('parameters').get('archive_mode')}
        self.config.get('parameters')['archive_mode'] = 'off'

        # and don't load shared_preload_libraries which don't exist in the old version
        self.adjust_shared_preload_libraries(float(version))

        return self.bootstrap.bootstrap(config)

    def get_cluster_version(self):
        """
        Get the version of the cluster.

        Returns: str: The version of the cluster.
        """
        with open(self._version_file) as f:
            return f.read().strip()

    def set_bin_dir(self, version):
        """
        Sets the binary directory for the specified version.

        :param version: The string version of PostgreSQL.
        """
        from spilo_commons import get_bin_dir

        self._old_bin_dir = self._bin_dir
        self._bin_dir = get_bin_dir(version)

    @property
    def local_conn_kwargs(self):
        """
        Returns the connection kwargs for the local database.

        The returned kwargs include options for synchronous_commit, statement_timeout, and search_path.
        The connect_timeout option is removed from the kwargs.

        Returns: dict: The connection kwargs for the local database.
        """
        conn_kwargs = self.config.local_connect_kwargs
        conn_kwargs['options'] = '-c synchronous_commit=local -c statement_timeout=0 -c search_path='
        conn_kwargs.pop('connect_timeout', None)
        return conn_kwargs

    def _get_all_databases(self):
        """
        Retrieve a list of all databases in the PostgreSQL cluster.

        Returns: list: A list of database names.
        """
        return [d[0] for d in self.query('SELECT datname FROM pg_catalog.pg_database WHERE datallowconn')]

    def drop_possibly_incompatible_extensions(self):
        """
        Drops extensions from the cluster which could be incompatible.
        It iterates over all databases in the cluster and drops the extensions
        specified in the `_INCOMPATIBLE_EXTENSIONS` list if they exist.
        It uses the `patroni.postgresql.connection.get_connection_cursor` function to establish a connection to each database.
        """
        from patroni.postgresql.connection import get_connection_cursor

        logger.info('Dropping extensions from the cluster which could be incompatible')
        conn_kwargs = self.local_conn_kwargs

        for d in self._get_all_databases():
            conn_kwargs['dbname'] = d
            with get_connection_cursor(**conn_kwargs) as cur:
                for ext in self._INCOMPATIBLE_EXTENSIONS:
                    logger.info('Executing "DROP EXTENSION IF EXISTS %s" in the database="%s"', ext, d)
                    cur.execute("DROP EXTENSION IF EXISTS {0}".format(ext))

    def drop_possibly_incompatible_objects(self):
        """
        Drops objects from the cluster which could be incompatible.
        It iterates over all databases in the cluster and drops the objects from `_INCOMPATIBLE_EXTENSIONS`.
        It uses the `patroni.postgresql.connection.get_connection_cursor` function to establish a connection to each database.
        """
        from patroni.postgresql.connection import get_connection_cursor

        logger.info('Dropping objects from the cluster which could be incompatible')
        conn_kwargs = self.local_conn_kwargs

        for d in self._get_all_databases():
            conn_kwargs['dbname'] = d
            with get_connection_cursor(**conn_kwargs) as cur:

                cmd = "REVOKE EXECUTE ON FUNCTION pg_catalog.pg_switch_{0}() FROM admin".format(self.wal_name)
                logger.info('Executing "%s" in the database="%s"', cmd, d)
                cur.execute(cmd)

                logger.info('Executing "DROP FUNCTION metric_helpers.pg_stat_statements" in the database="%s"', d)
                cur.execute("DROP FUNCTION IF EXISTS metric_helpers.pg_stat_statements(boolean) CASCADE")

                for ext in ('pg_stat_kcache', 'pg_stat_statements') + self._INCOMPATIBLE_EXTENSIONS:
                    logger.info('Executing "DROP EXTENSION IF EXISTS %s" in the database="%s"', ext, d)
                    cur.execute("DROP EXTENSION IF EXISTS {0}".format(ext))

                cur.execute("SELECT oid::regclass FROM pg_catalog.pg_class"
                            " WHERE relpersistence = 'u' AND relkind = 'r'")
                for unlogged in cur.fetchall():
                    logger.info('Truncating unlogged table %s', unlogged[0])
                    try:
                        cur.execute('TRUNCATE {0}'.format(unlogged[0]))
                    except Exception as e:
                        logger.error('Failed: %r', e)

    def update_extensions(self):
        """
        Updates the extensions in the PostgreSQL databases.
        Connects to each database and executes the 'ALTER EXTENSION UPDATE' command
        for each extension found in the database.

        Raises: Any exception raised during the execution of the 'ALTER EXTENSION UPDATE' command.
        """
        from patroni.postgresql.connection import get_connection_cursor

        conn_kwargs = self.local_conn_kwargs

        for d in self._get_all_databases():
            conn_kwargs['dbname'] = d
            with get_connection_cursor(**conn_kwargs) as cur:
                cur.execute('SELECT quote_ident(extname) FROM pg_catalog.pg_extension')
                for extname in cur.fetchall():
                    query = 'ALTER EXTENSION {0} UPDATE'.format(extname[0])
                    logger.info("Executing '%s' in the database=%s", query, d)
                    try:
                        cur.execute(query)
                    except Exception as e:
                        logger.error('Failed: %r', e)

    @staticmethod
    def remove_new_data(d):
        """
        Remove the new data directory.

        :param d: The string directory path to be removed.
        """
        if d.endswith('_new') and os.path.isdir(d):
            shutil.rmtree(d)

    def cleanup_new_pgdata(self):
        """
        Cleans up the new PostgreSQL data directory.
        If the `_new_data_dir` attribute is set, this method removes the new data directory.
        """
        if getattr(self, '_new_data_dir', None):
            self.remove_new_data(self._new_data_dir)

    def cleanup_old_pgdata(self):
        """
        Removes the old data directory if it exists.

        Returns: bool: True if the old data directory was successfully removed, False otherwise.
        """
        if os.path.exists(self._old_data_dir):
            logger.info('Removing %s', self._old_data_dir)
            shutil.rmtree(self._old_data_dir)
        return True

    def switch_pgdata(self):
        """
        Switches the PostgreSQL data directory by renaming the current data directory to a old directory,
        and renaming the new data directory to the current data directory.
        """
        self._old_data_dir = self._data_dir + '_old'
        self.cleanup_old_pgdata()
        os.rename(self._data_dir, self._old_data_dir)
        if getattr(self, '_new_data_dir', None):
            os.rename(self._new_data_dir, self._data_dir)
        self.configure_server_parameters()
        return True

    def switch_back_pgdata(self):
        """
        Switches back to the original data directory by renaming the new data directory to the original data directory name.
        If the original data directory exists, it is renamed to a backup name before renaming the new data directory.
        """
        if os.path.exists(self._data_dir):
            self._new_data_dir = self._data_dir + '_new'
            self.cleanup_new_pgdata()
            os.rename(self._data_dir, self._new_data_dir)
        os.rename(self._old_data_dir, self._data_dir)

    def pg_upgrade(self, check=False):
        """
        It performs the pg_upgrade process using the `pg_upgrade` command to perform the upgrade process.
        The `psutil.cpu_count` set the number of CPUs to use in the upgrade, `shutil.rmtree` remove the upgrade directory, 
        `os.makedirs` creates the upgrade directory, `os.chdir` changes the current directory to the upgrade directory, 
        `subprocess.call` execute the `pg_upgrade` command.
        
        :param check: A boolean value indicating whether to perform a check or not.

        Returns: bool: True if the pg_upgrade process was successful, False otherwise.
        """
        upgrade_dir = self._data_dir + '_upgrade'
        if os.path.exists(upgrade_dir) and os.path.isdir(upgrade_dir):
            shutil.rmtree(upgrade_dir)

        os.makedirs(upgrade_dir)

        old_cwd = os.getcwd()
        os.chdir(upgrade_dir)

        pg_upgrade_args = ['-k', '-j', str(psutil.cpu_count()),
                           '-b', self._old_bin_dir, '-B', self._bin_dir,
                           '-d', self._data_dir, '-D', self._new_data_dir,
                           '-O', "-c timescaledb.restoring='on'",
                           '-O', "-c archive_mode='off'"]
        if 'username' in self.config.superuser:
            pg_upgrade_args += ['-U', self.config.superuser['username']]

        if check:
            pg_upgrade_args += ['--check']
        else:
            self.config.write_postgresql_conf()

        logger.info('Executing pg_upgrade%s', (' --check' if check else ''))
        if subprocess.call([self.pgcommand('pg_upgrade')] + pg_upgrade_args) == 0:
            os.chdir(old_cwd)
            shutil.rmtree(upgrade_dir)
            return True

    def prepare_new_pgdata(self, version):
        from spilo_commons import append_extensions

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

        # shared_preload_libraries for the old cluster, cleaned from incompatible/missing libs
        old_shared_preload_libraries = self.config.get('parameters').get('shared_preload_libraries')

        # restore original values of archive_mode and shared_preload_libraries
        if getattr(self, '_old_config_values', None):
            for name, value in self._old_config_values.items():
                if value is None:
                    self.config.get('parameters').pop(name)
                else:
                    self.config.get('parameters')[name] = value

        # for the new version we maybe need to add some libs to the shared_preload_libraries
        shared_preload_libraries = self.config.get('parameters').get('shared_preload_libraries')
        if shared_preload_libraries:
            self._old_shared_preload_libraries = self.config.get('parameters')['shared_preload_libraries'] =\
                append_extensions(shared_preload_libraries, float(version))
            self.no_bg_mon()

        if not self.bootstrap._initdb(initdb_config):
            return False
        self.bootstrap._running_custom_bootstrap = False

        # Copy old configs. XXX: some parameters might be incompatible!
        for f in os.listdir(self._new_data_dir):
            if f.startswith('postgresql.') or f.startswith('pg_hba.conf') or f == 'patroni.dynamic.json':
                shutil.copy(os.path.join(self._new_data_dir, f), os.path.join(self._data_dir, f))

        self.config.write_postgresql_conf()
        self._new_data_dir, self._data_dir = self._data_dir, self._new_data_dir
        self.config._postgresql_conf = old_postgresql_conf
        self._version_file = old_version_file

        if old_shared_preload_libraries:
            self.config.get('parameters')['shared_preload_libraries'] = old_shared_preload_libraries
            self.no_bg_mon()
        self.configure_server_parameters()
        return True

    def do_upgrade(self):
        """
        Performs the upgrade process for the PostgreSQL appliance.

        Returns: bool: True if the upgrade process is successful, False otherwise.
        """
        return self.pg_upgrade() and self.restore_shared_preload_libraries()\
                 and self.switch_pgdata() and self.cleanup_old_pgdata()

    def analyze(self, in_stages=False):
        vacuumdb_args = ['--analyze-in-stages'] if in_stages else []
        logger.info('Rebuilding statistics (vacuumdb%s)', (' ' + vacuumdb_args[0] if in_stages else ''))
        if 'username' in self.config.superuser:
            vacuumdb_args += ['-U', self.config.superuser['username']]
        vacuumdb_args += ['-Z', '-j']

        # vacuumdb is processing databases sequantially, while we better do them in parallel,
        # because it will help with the case when there are multiple databases in the same cluster.
        single_worker_dbs = ('postgres', 'template1')
        databases = self._get_all_databases()
        db_count = len([d for d in databases if d not in single_worker_dbs])
        # calculate concurrency per database, except always existing "single_worker_dbs" (they'll get always 1 worker)
        concurrency = str(max(1, int(psutil.cpu_count()/max(1, db_count))))
        procs = []
        for d in databases:
            j = '1' if d in single_worker_dbs else concurrency
            try:
                procs.append(subprocess.Popen([self.pgcommand('vacuumdb')] + vacuumdb_args + [j, '-d', d]))
            except Exception:
                pass
        for proc in procs:
            try:
                proc.wait()
            except Exception:
                pass


def PostgresqlUpgrade(config):
    """
    Upgrade the PostgreSQL database using the provided configuration.

    :param config: A dictionary containing the PostgreSQL configuration.

    Returns: _PostgresqlUpgrade: An instance of the _PostgresqlUpgrade class.
    """
    config['postgresql'].update({'callbacks': {}, 'pg_ctl_timeout': 3600*24*7})

    # avoid unnecessary interactions with PGDATA and postgres
    is_running = _PostgresqlUpgrade.is_running
    _PostgresqlUpgrade.is_running = lambda s: False
    try:
        return _PostgresqlUpgrade(config['postgresql'])
    finally:
        _PostgresqlUpgrade.is_running = is_running
