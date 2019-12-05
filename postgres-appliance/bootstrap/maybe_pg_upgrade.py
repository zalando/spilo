#!/usr/bin/env python
import logging
import sys

logger = logging.getLogger(__name__)


def main():
    from pg_upgrade import PostgresqlUpgrade
    from patroni.config import Config
    from patroni.utils import polling_loop

    config = Config(sys.argv[1])
    config['postgresql'].update({'callbacks': {}, 'pg_ctl_timeout': 3600*24*7})
    upgrade = PostgresqlUpgrade(config['postgresql'])

    bin_version = upgrade.get_binary_version()
    cluster_version = upgrade.get_cluster_version()

    if cluster_version == bin_version:
        return 0

    logger.info('Cluster version: %s, bin version: %s', cluster_version, bin_version)
    assert float(cluster_version) < float(bin_version)

    logger.info('Trying to start the cluster with old postgres')
    if not upgrade.start_old_cluster(config['bootstrap'], cluster_version):
        raise Exception('Failed to start the cluster with old postgres')

    for _ in polling_loop(upgrade.config.get('pg_ctl_timeout'), 10):
        upgrade.reset_cluster_info_state()
        if upgrade.is_leader():
            break
        logger.info('waiting for end of recovery of the old cluster')

    if not upgrade.bootstrap.call_post_bootstrap(config['bootstrap']):
        upgrade.stop(block_callbacks=True, checkpoint=False)
        raise Exception('Failed to run bootstrap.post_init')

    locale = upgrade.query('SHOW lc_collate').fetchone()[0]
    encoding = upgrade.query('SHOW server_encoding').fetchone()[0]
    initdb_config = [{'locale': locale}, {'encoding': encoding}]
    if upgrade.query("SELECT current_setting('data_checksums')::bool").fetchone()[0]:
        initdb_config.append('data-checksums')

    logger.info('Dropping objects from the cluster which could be incompatible')
    try:
        upgrade.drop_possibly_incompatible_objects()
    except Exception:
        upgrade.stop(block_callbacks=True, checkpoint=False)
        raise

    logger.info('Doing a clean shutdown of the cluster before pg_upgrade')
    if not upgrade.stop(block_callbacks=True, checkpoint=False):
        raise Exception('Failed to stop the cluster with old postgres')

    logger.info('initdb config: %s', initdb_config)

    logger.info('Executing pg_upgrade')
    if not upgrade.do_upgrade(bin_version, initdb_config):
        raise Exception('Failed to upgrade cluster from {0} to {1}'.format(cluster_version, bin_version))

    logger.info('Starting the cluster with new postgres after upgrade')
    if not upgrade.start():
        raise Exception('Failed to start the cluster with new postgres')
    upgrade.analyze()


def call_maybe_pg_upgrade():
    import inspect
    import os
    import subprocess

    my_name = os.path.abspath(inspect.getfile(inspect.currentframe()))
    ret = subprocess.call([sys.executable, my_name, os.path.join(os.getenv('PGHOME'), 'postgres.yml')])
    if ret != 0:
        logger.error('%s script failed', my_name)
    return ret


if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s maybe_pg_upgrade %(levelname)s: %(message)s', level='INFO')
    main()
