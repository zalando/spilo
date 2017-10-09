#!/usr/bin/env python

import argparse
from collections import namedtuple
import logging
import os
import subprocess

logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

def read_configuration():
    parser = argparse.ArgumentParser(description="Script to clone from another cluster using pg_basebackup")
    parser.add_argument('--scope', required=True, help='target cluster name')
    parser.add_argument('--datadir', required=True, help='target cluster postgres data directory')
    parser.add_argument('--bindir', default='', help='the directory with pg_basebackup')
    parser.add_argument('--from-pgpass', required=True, help='path to the pgpass file containing credentials for the instance to be cloned')
    args = parser.parse_args()

    options = namedtuple('Options', 'name datadir bindir pgpassfile')

    result=options(name=args.scope, datadir=args.datadir, bindir=args.bindir, pgpassfile=args.from_pgpass)
    return result

def parse_pgpass_file(pgpassfile):
    with open(pgpassfile, 'r') as f:
        line = f.readline()
        return parse_pgpass_line(line)


def parse_pgpass_line(line):
    """ parses a single pgpass line and returns a connection string (without the password)

        >>> parse_pgpass_line('127.0.0.1:5432:db:user:pass')
        pgpass(host='127.0.0.1', port='5432', dbname='db', user='user')
        >>> parse_pgpass_line('\:\:1:5432:"ba\\\\\\\\z":qiz:foo')
        pgpass(host='::1', port='5432', dbname='"ba\\\\z"', user='qiz')
        >>> parse_pgpass_line('127.0.0.1:1234:db:user:')
        Traceback (most recent call last):
            ...
        Exception: pgpass file contains an empty field
        >>> parse_pgpass_line('127\.0.0.1:1234:db:user:')
        Traceback (most recent call last):
            ...
        Exception: pgpass file has unescaped '\\' character
    """

    fields = []
    escape = False
    current = []
    for c in line:
        if c == ':' and not escape:
            if len(current) == 0:
                raise Exception("pgpass file contains an empty field")
            fields.append(''.join(current))
            current = []
            continue
        if c == '\\' and not escape:
            escape = True
            continue
        if escape:
            if c not in (':', '\\'):
                raise Exception("pgpass file has unescaped '\\' character")
            escape = False
        current.append(c)
    # process the last field in line
    if escape:
        raise Exception("pgpass file has unescaped '\\' character")
    if len(current) == 0:
        raise Exception("pgpass file contains an empty field")
    fields.append(''.join(current))
    if len(fields) != 5:
        raise Exception("pgpass file must be in a format 'hostname:port:database:username:password'")
    return namedtuple('pgpass', 'host port dbname user')._make(fields[:4])

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
    pgpass = parse_pgpass_file(options.pgpassfile)
    connection = []
    for attname in ('host', 'port', 'user', 'dbname'):
        attvalue = getattr(pgpass, attname)
        if attvalue and attvalue != '*':
            connection.append('{0}={1}'.format(attname, escape_value(attvalue)))

    return ' '.join(connection), {'PGPASSFILE': options.pgpassfile}

def run_basebackup(options):
    pg_basebackup = os.path.join(options.bindir, 'pg_basebackup')

    connstr, env = prepare_connection(options)
    logger.info("cloning cluster {0} from \"{1}\"".format(options.name, connstr))
    ret = subprocess.call([pg_basebackup, '--pgdata={0}'.format(options.datadir), '-X', 'stream', '--dbname={0}'.format(connstr), '-w'], env=env)
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