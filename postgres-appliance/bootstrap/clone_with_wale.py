#!/usr/bin/env python

import argparse
import csv
import logging
import os
import re
import shlex
import subprocess
import sys

from maybe_pg_upgrade import call_maybe_pg_upgrade

from collections import namedtuple
from dateutil.parser import parse

logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)


def read_configuration():
    parser = argparse.ArgumentParser(description="Script to clone from S3 with support for point-in-time-recovery")
    parser.add_argument('--scope', required=True, help='target cluster name')
    parser.add_argument('--datadir', required=True, help='target cluster postgres data directory')
    parser.add_argument('--recovery-target-time',
                        help='the timestamp up to which recovery will proceed (including time zone)',
                        dest='recovery_target_time_string')
    parser.add_argument('--dry-run', action='store_true', help='find a matching backup and build the wal-e '
                        'command to fetch that backup without running it')
    args = parser.parse_args()

    options = namedtuple('Options', 'name datadir recovery_target_time dry_run')
    if args.recovery_target_time_string:
        recovery_target_time = parse(args.recovery_target_time_string)
        if recovery_target_time.tzinfo is None:
            raise Exception("recovery target time must contain a timezone")
    else:
        recovery_target_time = None

    return options(args.scope, args.datadir, recovery_target_time, args.dry_run)


def build_wale_command(command, datadir=None, backup=None):
    cmd = ['wal-g' if os.getenv('USE_WALG_RESTORE') == 'true' else 'wal-e'] + [command]
    if command == 'backup-fetch':
        if datadir is None or backup is None:
            raise Exception("backup-fetch requires datadir and backup arguments")
        cmd.extend([datadir, backup])
    elif command != 'backup-list':
        raise Exception("invalid {0} command {1}".format(cmd[0], command))
    return cmd


def fix_output(output):
    """WAL-G is using spaces instead of tabs and writes some garbage before the actual header"""

    started = None
    for line in output.decode('utf-8').splitlines():
        if not started:
            started = re.match(r'^name\s+last_modified\s+', line) or re.match(r'^name\s+modified\s+', line)
            if started:
                line = line.replace(' modified ', ' last_modified ')
        if started:
            yield '\t'.join(line.split())


def choose_backup(backup_list, recovery_target_time):
    """ pick up the latest backup file starting before time recovery_target_time"""

    match_timestamp = match = None
    for backup in backup_list:
        last_modified = parse(backup['last_modified'])
        if last_modified < recovery_target_time:
            if match is None or last_modified > match_timestamp:
                match = backup
                match_timestamp = last_modified
    if match is not None:
        return match['name']


def list_backups(env):
    backup_list_cmd = build_wale_command('backup-list')
    output = subprocess.check_output(backup_list_cmd, env=env)
    reader = csv.DictReader(fix_output(output), dialect='excel-tab')
    return list(reader)


def get_clone_envdir():
    from spilo_commons import get_patroni_config

    config = get_patroni_config()
    restore_command = shlex.split(config['bootstrap']['clone_with_wale']['recovery_conf']['restore_command'])
    if len(restore_command) > 4 and restore_command[0] == 'envdir':
        return restore_command[1]
    raise Exception('Failed to find clone envdir')


def get_possible_versions():
    from spilo_commons import LIB_DIR, get_binary_version, get_bin_dir, get_patroni_config

    config = get_patroni_config()

    max_version = float(get_binary_version(config.get('postgresql', {}).get('bin_dir')))

    versions = {}

    for d in os.listdir(LIB_DIR):
        try:
            ver = get_binary_version(get_bin_dir(d))
            fver = float(ver)
            if fver <= max_version:
                versions[fver] = ver
        except Exception:
            pass

    # return possible versions in reversed order, i.e. 12, 11, 10, 9.6, and so on
    return [ver for _, ver in sorted(versions.items(), reverse=True)]


def get_wale_environments(env):
    use_walg = env.get('USE_WALG_RESTORE') == 'true'
    prefix = 'WALG_' if use_walg else 'WALE_'
    # len('WALE__PREFIX') = 12
    names = [name for name in env.keys() if name.endswith('_PREFIX') and name.startswith(prefix) and len(name) > 12]
    if len(names) != 1:
        raise Exception('Found find {0} {1}*_PREFIX environment variables, expected 1'
                        .format(len(names), prefix))

    name = names[0]
    orig_value = env[name]
    value = orig_value.rstrip('/')

    if '/spilo/' in value and value.endswith('/wal'):  # path crafted in the configure_spilo.py?
        # Try all versions descending if we don't know the version of the source cluster
        for version in get_possible_versions():
            yield name, '{0}/{1}/'.format(value, version)

    # Last, try the original value
    yield name, orig_value


def find_backup(recovery_target_time, env):
    old_value = None
    for name, value in get_wale_environments(env):
        logger.info('Trying %s for clone', value)
        if not old_value:
            old_value = env[name]
        env[name] = value
        backup_list = list_backups(env)
        if backup_list:
            if recovery_target_time:
                backup = choose_backup(backup_list, recovery_target_time)
                if backup:
                    return backup, (name if value != old_value else None)
            else:  # We assume that the LATEST backup will be for the biggest postgres version!
                return 'LATEST', (name if value != old_value else None)
    if recovery_target_time:
        raise Exception('Could not find any backups prior to the point in time {0}'.format(recovery_target_time))
    raise Exception('Could not find any backups')


def run_clone_from_s3(options):
    env = os.environ.copy()

    backup_name, update_envdir = find_backup(options.recovery_target_time, env)

    backup_fetch_cmd = build_wale_command('backup-fetch', options.datadir, backup_name)
    logger.info("cloning cluster %s using %s", options.name, ' '.join(backup_fetch_cmd))
    if not options.dry_run:
        ret = subprocess.call(backup_fetch_cmd, env=env)
        if ret != 0:
            raise Exception("wal-e backup-fetch exited with exit code {0}".format(ret))

        if update_envdir:  # We need to update file in the clone envdir or restore_command will fail!
            envdir = get_clone_envdir()
            with open(os.path.join(envdir, update_envdir), 'w') as f:
                f.write(env[update_envdir])
    return 0


def main():
    options = read_configuration()
    try:
        run_clone_from_s3(options)
    except Exception:
        logger.exception("Clone failed")
        return 1
    return call_maybe_pg_upgrade()


if __name__ == '__main__':
    sys.exit(main())
