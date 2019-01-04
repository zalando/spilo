#!/usr/bin/env python
import logging
import sys

logger = logging.getLogger(__name__)


def main():
    from patroni.config import Config
    from patroni.utils import polling_loop
    from pg_upgrade import PostgresqlUpgrade

    config = Config()
    upgrade = PostgresqlUpgrade(config['postgresql'])

    bin_version = upgrade.get_binary_version()
    cluster_version = upgrade.get_cluster_version()
    if cluster_version == bin_version:
        return 0

    assert float(cluster_version) < float(bin_version)

    upgrade.set_bin_dir(cluster_version)
    upgrade.config['listen'] = 'localhost'
    upgrade.config['pg_ctl_timeout'] = 3600*24*7
    upgrade.config['callbacks'] = {}

    bootstrap_config = config['bootstrap']
    bootstrap_config[bootstrap_config['method']]['command'] = 'true'
    if not upgrade.bootstrap(bootstrap_config):
        raise Exception('Failed to start cluster with old postgres')

    for _ in polling_loop(upgrade.config['pg_ctl_timeout'], 10):
        upgrade.reset_cluster_info_state()
        if upgrade.is_leader():
            break
        logger.info('waiting for end of recovery after bootstrap')

    locale = upgrade.query('SHOW lc_collate').fetchone()[0]
    encoding = upgrade.query('SHOW server_encoding').fetchone()[0]
    initdb_config = {'initdb': [{'locale': locale}, {'encoding': encoding}]}
    if upgrade.query('SHOW data_checksums').fetchone()[0]:
        initdb_config['initdb'].append('data-checksums')

    if not upgrade.run_bootstrap_post_init(bootstrap_config):
        raise Exception('Failed to run bootstrap.post_init')

    if not upgrade.stop(block_callbacks=True, checkpoint=False):
        raise Exception('Failed to stop cluster with old postgres')

    return upgrade.do_upgrade(bin_version, initdb_config)


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
    if len(sys.argv) > 5 and sys.argv[1] == 'pg_ctl_start':
        from patroni import pg_ctl_start
        pg_ctl_start(sys.argv[2:])
    else:
        sys.exit(main())
