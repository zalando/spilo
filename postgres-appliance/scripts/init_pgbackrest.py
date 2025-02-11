#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# This script is called after configure_spilo.py and within the pgbackrest environment.
# Therefore, all relevant configuration paramters are taken from the environment

import json
import subprocess

def stanza_exists_status():
    stanza_info_command = ['pgbackrest', 'info', '--output=json']
    stanza_info = subprocess.check_output(stanza_info_command).decode('utf-8')
    stanza_info = json.loads(stanza_info)
    stanza_status = stanza_info[0]['status']['code']
    return bool(stanza_status == 0)

def stanza_create():
    stanza_create_command = ['pgbackrest', 'stanza-create']
    return bool(subprocess.check_call(stanza_create_command) == 0)

def stanza_backup():
    stanza_backup_command = ['pgbackrest', 'backup']
    return bool(subprocess.check_call(stanza_backup_command) == 0)

def main():
    if not stanza_exists_status():
        if not stanza_create():
            raise Exception('Failed to create stanza')
    if not stanza_backup():
        raise Exception('Failed to backup stanza')


if __name__ == '__main__':
    main()