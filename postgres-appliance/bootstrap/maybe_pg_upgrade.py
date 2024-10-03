#!/usr/bin/env python
import glob
import logging
import os
import subprocess
import sys

logger = logging.getLogger(__name__)


def tail_postgres_logs():
    logdir = os.environ.get('PGLOG', '/home/postgres/pgdata/pgroot/pg_log')
    csv_files = glob.glob(os.path.join(logdir, '*.csv'))
    # Find the last modified CSV file
    logfile = max(csv_files, key=os.path.getmtime)
    return subprocess.check_output(['tail', '-n5', logfile]).decode('utf-8')


def wait_end_of_recovery(postgresql):
    from patroni.utils import polling_loop

    for _ in polling_loop(postgresql.config.get('pg_ctl_timeout'), 10):
        postgresql.reset_cluster_info_state(None)
        if postgresql.is_primary():
            break
        logger.info('waiting for end of recovery of the old cluster')


def perform_pitr(postgresql, cluster_version, bin_version, config):
    logger.info('Trying to perform point-in-time recovery')

    config[config['method']]['command'] = 'true'
    try:
        if bin_version == cluster_version:
            if not postgresql.bootstrap.bootstrap(config):
                raise Exception('Point-in-time recovery failed')
        elif not postgresql.start_old_cluster(config, cluster_version):
            raise Exception('Failed to start the cluster with old postgres')
        return wait_end_of_recovery(postgresql)
    except Exception:
        logs = tail_postgres_logs()
        # Spilo has no other locales except en_EN.UTF-8, therefore we are safe here.
        if int(cluster_version) >= 13 and 'recovery ended before configured recovery target was reached' in logs:
            # Starting from version 13 Postgres stopped promoting when recovery target wasn't reached.
            # In order to improve the user experience we reset all possible recovery targets and retry.
            recovery_conf = config[config['method']].get('recovery_conf', {})
            if recovery_conf:
                for target in ('name', 'time', 'xid', 'lsn'):
                    recovery_conf['recovery_target_' + target] = ''
            logger.info('Retrying point-in-time recovery without target')
            if not postgresql.bootstrap.bootstrap(config):
                raise Exception('Point-in-time recovery failed.\nLOGS:\n--\n' + tail_postgres_logs())
            return wait_end_of_recovery(postgresql)
        else:
            raise Exception('Point-in-time recovery failed.\nLOGS:\n--\n' + logs)


def main():
    from pg_upgrade import PostgresqlUpgrade
    from patroni.config import Config
    from spilo_commons import get_binary_version

    config = Config(sys.argv[1])
    upgrade = PostgresqlUpgrade(config)

    bin_version = get_binary_version(upgrade.pgcommand(''))
    cluster_version = upgrade.get_cluster_version()

    logger.info('Cluster version: %s, bin version: %s', cluster_version, bin_version)
    assert float(cluster_version) <= float(bin_version)

    perform_pitr(upgrade, cluster_version, bin_version, config['bootstrap'])

    if cluster_version == bin_version:
        return 0

    if not upgrade.bootstrap.call_post_bootstrap(config['bootstrap']):
        upgrade.stop(block_callbacks=True, checkpoint=False)
        raise Exception('Failed to run bootstrap.post_init')

    if not upgrade.prepare_new_pgdata(bin_version):
        raise Exception('initdb failed')

    try:
        upgrade.drop_possibly_incompatible_objects()
    except Exception:
        upgrade.stop(block_callbacks=True, checkpoint=False)
        raise

    logger.info('Doing a clean shutdown of the cluster before pg_upgrade')
    if not upgrade.stop(block_callbacks=True, checkpoint=False):
        raise Exception('Failed to stop the cluster with old postgres')

    if not upgrade.do_upgrade():
        raise Exception('Failed to upgrade cluster from {0} to {1}'.format(cluster_version, bin_version))

    logger.info('Starting the cluster with new postgres after upgrade')
    if not upgrade.start():
        raise Exception('Failed to start the cluster with new postgres')

    try:
        upgrade.update_extensions()
    except Exception as e:
        logger.error('Failed to update extensions: %r', e)

    upgrade.analyze()


def call_maybe_pg_upgrade():
    import inspect
    import os
    import subprocess

    from spilo_commons import PATRONI_CONFIG_FILE

    my_name = os.path.abspath(inspect.getfile(inspect.currentframe()))
    ret = subprocess.call([sys.executable, my_name, PATRONI_CONFIG_FILE])
    if ret != 0:
        logger.error('%s script failed', my_name)
    return ret


if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s maybe_pg_upgrade %(levelname)s: %(message)s', level='INFO')
    main()
