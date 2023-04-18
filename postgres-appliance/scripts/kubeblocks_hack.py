#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import yaml

from pyjavaproperties import Properties

_DYNAMIC_PARAMETERS = [
    'archive_mode',
    'archive_timeout',
    'wal_level',
    'wal_log_hints',
    'wal_compression',
    'max_wal_senders',
    'max_connections',
    'max_replication_slots',
    'hot_standby',
    'tcp_keepalives_idle',
    'tcp_keepalives_interval',
    'log_line_prefix',
    'log_checkpoints',
    'log_lock_waits',
    'log_min_duration_statement',
    'log_autovacuum_min_duration',
    'log_connections',
    'log_disconnections',
    'log_statement',
    'log_temp_files',
    'track_functions',
    'checkpoint_completion_target',
    'autovacuum_max_workers',
    'autovacuum_vacuum_scale_factor',
    'autovacuum_analyze_scale_factor',
]

_LOCAL_PARAMETERS = [
    'archive_command',
    'shared_buffers',
    'logging_collector',
    'log_destination',
    'log_directory',
    'log_filename',
    'log_file_mode',
    'log_rotation_age',
    'log_truncate_on_rotation',
    'ssl',
    'ssl_ca_file',
    'ssl_crl_file',
    'ssl_cert_file',
    'ssl_key_file',
    'shared_preload_libraries',
    'bg_mon.listen_address',
    'bg_mon.history_buckets',
    'pg_stat_statements.track_utility',
    'extwlist.extensions',
    'extwlist.custom_path',
]


def _process_pg_parameters(parameters, param_limits):
    return {name: value.strip("'") for name, value in (parameters or {}).items()
            if name in param_limits}


def read_file_lines(file):
    ret = []
    for line in file.readlines():
        line = line.strip()
        if line and not line.startswith('#'):
            ret.append(line)
    return ret


def update_dynamic_config(props, config):
    if 'parameters' not in config:
        config['parameters'] = {}
    config['parameters'].update(_process_pg_parameters(props.getPropertyDict(), _DYNAMIC_PARAMETERS))


def update_local_config(props, config):
    if 'parameters' not in config:
        config['parameters'] = {}
    config['parameters'].update(_process_pg_parameters(props.getPropertyDict(), _LOCAL_PARAMETERS))


def prepare(config_file, local_config):
    if 'postgresql' not in local_config:
        local_config['postgresql'] = {}

    if 'bootstrap' not in local_config:
        local_config['bootstrap'] = {}

    postgresql = local_config['postgresql']
    # postgresql['config_dir'] = _PG_CONF_DIR
    if 'custom_conf' not in postgresql:
        postgresql['custom_conf'] = config_file

    props = Properties()
    # parse postgresql.conf
    with open(config_file, 'r') as conf:
        props.load(conf)

    if 'dcs' not in local_config['bootstrap']:
        local_config['bootstrap']['dcs'] = {}

    dynamic_config = local_config['bootstrap']['dcs'].get('postgresql', {})

    # update patroni dynamic config to local_config['bootstrap']['dcs']['postgresql']['parameters']
    update_dynamic_config(props, dynamic_config)
    local_config['bootstrap']['dcs']['postgresql'] = dynamic_config

    # update patroni dynamic config to local_config['postgresql']['parameters']
    update_local_config(props, postgresql)

    # print kubeblocks generated local_config
    print(yaml.dump(local_config, default_flow_style=False))
