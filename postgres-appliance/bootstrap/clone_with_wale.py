#!/usr/bin/env python

import argparse
import csv
import logging
import os
import subprocess

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
    cmd = (['wal-g'] if os.getenv('USE_WALG_BACKUP') == 'true' else ['wal-e', '--aws-instance-profile']) + [command]
    if command == 'backup-fetch':
        if datadir is None or backup is None:
            raise Exception("backup-fetch requires datadir and backup arguments")
        cmd.extend([datadir, backup])
    elif command != 'backup-list':
        raise Exception("invalid {0} command {1}".format(cmd[0], command))
    return cmd


def choose_backup(output, recovery_target_time):
    """ pick up the latest backup file starting before time recovery_target_time"""
    reader = csv.DictReader(output.decode('utf-8').splitlines(), dialect='excel-tab')
    backup_list = list(reader)
    if len(backup_list) <= 0:
        raise Exception("wal-e could not found any backups")
    match_timestamp = match = None
    for backup in backup_list:
        last_modified = parse(backup['last_modified'])
        if last_modified < recovery_target_time:
            if match is None or last_modified > match_timestamp:
                match = backup
                match_timestamp = last_modified
    if match is None:
        raise Exception("wal-e could not found any backups prior to the point in time {0}".format(recovery_target_time))
    return match['name']


def run_clone_from_s3(options):
    backup_name = 'LATEST'
    if options.recovery_target_time:
        backup_list_cmd = build_wale_command('backup-list')
        backup_list = subprocess.check_output(backup_list_cmd)
        backup_name = choose_backup(backup_list, options.recovery_target_time)
    backup_fetch_cmd = build_wale_command('backup-fetch', options.datadir, backup_name)
    logger.info("cloning cluster %s using %s", options.name, ' '.join(backup_fetch_cmd))
    if not options.dry_run:
        ret = subprocess.call(backup_fetch_cmd)
        if ret != 0:
            raise Exception("wal-e backup-fetch exited with exit code {0}".format(ret))
    return 0


def main():
    options = read_configuration()
    try:
        return run_clone_from_s3(options)
    except Exception:
        logger.exception("Clone failed")
        return 1


if __name__ == '__main__':
    main()
