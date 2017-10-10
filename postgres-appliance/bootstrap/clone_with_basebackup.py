#!/usr/bin/env python

import argparse
from collections import namedtuple
import logging
import subprocess

logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

def read_configuration():
    parser = argparse.ArgumentParser(description="Script to clone from another cluster using pg_basebackup")
    parser.add_argument('--scope', required=True, help='target cluster name', dest='name')
    parser.add_argument('--datadir', required=True, help='target cluster postgres data directory')
    parser.add_argument('--pgpass', required=True,
                        help='path to the pgpass file containing credentials for the instance to be cloned')
    parser.add_argument('--host', required=True, help='hostname or IP address of the master to connect to')
    parser.add_argument('--port', required=False, help='PostgreSQL port master listens to', default=5432)
    parser.add_argument('--dbname', required=False, help='PostgreSQL database to connect to', default='postgres')
    parser.add_argument('--user', required=True, help='PostgreSQL user to connect with')
    return parser.parse_args()

def escape_value(val):
    quote = False
    temp = []
    for c in val:
        if c.isspace():
            quote = True
        elif c in ('\'', '\\'):
            temp.append('\\')
        temp.append(c)
    result = ''.join(temp)
    return result if not quote else '\'{0}\''.format(result)

def prepare_connection(options):
    connection = []
    for attname in ('host', 'port', 'user', 'dbname'):
        attvalue = getattr(options, attname)
        connection.append('{0}={1}'.format(attname, escape_value(attvalue)))

    return ' '.join(connection), {'PGPASSFILE': options.pgpass}

def run_basebackup(options):
    connstr, env = prepare_connection(options)
    logger.info("cloning cluster {0} from \"{1}\"".format(options.name, connstr))
    ret = subprocess.call(['pg_basebackup', '--pgdata={0}'.format(options.datadir), '-X', 'stream', '--dbname={0}'.format(connstr), '-w'], env=env)
    if ret != 0:
        raise Exception("pg_basebackup exited with code={0}".format(ret))
    return 0

def main():
    options = read_configuration()
    try:
        return run_basebackup(options)
    except:
        logger.exception("Clone failed")
        return 1

if __name__ == '__main__':
    main()