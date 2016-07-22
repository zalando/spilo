#!/usr/bin/env python
# -*- coding: utf-8 -*-

import argparse
import yaml


# destination: source
keys_move = {
    "bootstrap.dcs.ttl": "ttl",
    "bootstrap.dcs.loop_wait": "loop_wait",
    "bootstrap.dcs.maximum_lag_on_failover": "postgresql.maximum_lag_on_failover",
    "bootstrap.dcs.postgresql.parameters": "postgresql.parameters",
    "bootstrap.dcs.postgresql.recovery_conf": "postgresql.recovery_conf",
    "bootstrap.initdb": "postgresql.initdb",
    "bootstrap.users.admin.password": "postgresql.admin.password",
    "postgresql.authentication.superuser": "postgresql.superuser",
    "postgresql.authentication.replication": "postgresql.replication",
}

keys_delete = [
    "postgresql.admin",
    "postgresql.authentication.replication.network",
    "postgresql.authentication.superuser.network",
]

keys_add = {
    "bootstrap.users.admin.options": ["createrole", "createdb"],
    "bootstrap.dcs.postgresql.use_pg_rewind": True,
    "bootstrap.dcs.postgresql.use_slots": True,
    "bootstrap.dcs.retry_timeout": 10,
}


def get_value(d, path):
    for key in path:
        d = d[key]

    return d


def set_value(d, path, value):
    if not path:
        return value

    cur_key = path.pop(0)
    d[cur_key] = set_value({} if cur_key not in d else d[cur_key], path, value)

    return d


def remove_key(d, path):
    cur_key = path.pop(0)
    if not path:
        d.pop(cur_key, None)
        return d
    d[cur_key] = remove_key(d[cur_key], path)

    return d


def parse_args():
    argp = argparse.ArgumentParser(description='Patroni config migration utility')

    argp.add_argument('config', type=str, help="Pre v1.0 configuration file")
    args = vars(argp.parse_args())
    return args


def main():
    args = parse_args()
    with open(args['config'], 'r') as stream:
        old_config = yaml.load(stream)

    config = old_config.copy()

    for new, old in keys_move.items():
        value = get_value(old_config, old.split('.'))
        set_value(config, new.split('.'), value)
        remove_key(config, old.split('.'))

    for key in keys_delete:
        remove_key(config, key.split('.'))

    for key, value in keys_add.items():
        set_value(config, key.split('.'), value)

    print(yaml.dump(config, default_flow_style=False, width=120))


if __name__ == '__main__':
    main()
