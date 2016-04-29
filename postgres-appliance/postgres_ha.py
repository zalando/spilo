#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import re
import os
import socket
import subprocess

import yaml
import pystache
import requests


def write_certificates(environment):
    """Write SSL certificate to files

    If certificates are specified, they are written, otherwise
    dummy certificates are generated and written"""

    ssl_keys = ['SSL_CERTIFICATE', 'SSL_PRIVATE_KEY']
    if set(ssl_keys) <= set(environment):
        for k in ssl_keys:
            with open(environment[k + '_FILE'], 'w') as f:
                f.write(environment[k])
    else:
        openssl_cmd = [
            '/usr/bin/openssl',
            'req',
            '-nodes',
            '-new',
            '-x509',
            '-subj',
            '/CN=spilo.dummy.org',
            '-keyout',
            environment['SSL_PRIVATE_KEY_FILE'],
            '-out',
            environment['SSL_CERTIFICATE_FILE'],
        ]
        logging.info('Generating ssl certificate')
        p = subprocess.Popen(openssl_cmd, shell=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        output, _ = p.communicate()
        logging.debug(output)

    os.chmod(environment['SSL_PRIVATE_KEY_FILE'], 0o600)


def deep_update(a, b):
    """Updates data structures

    Dicts are merged, recursively
    List b is appended to a (except duplicates)
    For anything else, the value of a is returned"""

    if type(a) is dict and type(b) is dict:
        for key in b:
            if key in a:
                a[key] = deep_update(a[key], b[key])
            else:
                a[key] = b[key]
        return a
    if type(a) is list and type(b) is list:
        return a + [i for i in b if i not in a]

    return a if a is not None else b


TEMPLATE = \
    '''
ttl: &ttl 30
loop_wait: &loop_wait 10
scope: &scope '{{SCOPE}}'
restapi:
  listen: 0.0.0.0:{{APIPORT}}
  connect_address: {{instance_data.ip}}:{{APIPORT}}
postgresql:
  name: {{instance_data.id}}
  scope: *scope
  listen: 0.0.0.0:{{PGPORT}}
  connect_address: {{instance_data.ip}}:{{PGPORT}}
  data_dir: {{PGDATA}}
  initdb:
    - encoding: UTF8
    - locale: en_US.UTF-8
  pg_hba:
    - hostssl all all 0.0.0.0/0 md5
    - host    all all 0.0.0.0/0 md5
  superuser:
    username: postgres
    password: {{PGPASSWORD_SUPERUSER}}
  admin:
    username: admin
    password: {{PGPASSWORD_ADMIN}}
  replication:
    username: standby
    password: {{PGPASSWORD_STANDBY}}
    network: 0.0.0.0/0
  callbacks:
    on_start: patroni_aws
    on_stop: patroni_aws
    on_restart: patroni_aws
    on_role_change: patroni_aws
  wal_e:
    command: patroni_wale_restore
    envdir: {{WALE_ENV_DIR}}
    threshold_megabytes: {{WALE_BACKUP_THRESHOLD_MEGABYTES}}
    threshold_backup_size_percentage: {{WALE_BACKUP_THRESHOLD_PERCENTAGE}}
    use_iam: 1
    retries: 2
  parameters:
    archive_mode: 'on'
    wal_level: hot_standby
    archive_command: envdir "{{WALE_ENV_DIR}}" wal-e --aws-instance-profile wal-push "%p" -p 1
    max_wal_senders: 5
    wal_keep_segments: 8
    archive_timeout: 1800s
    max_connections: {{postgresql.parameters.max_connections}}
    max_replication_slots: 5
    hot_standby: 'on'
    tcp_keepalives_idle: 900
    tcp_keepalives_interval: 100
    ssl: 'on'
    ssl_cert_file: {{SSL_CERTIFICATE_FILE}}
    ssl_key_file: {{SSL_PRIVATE_KEY_FILE}}
    shared_buffers: {{postgresql.parameters.shared_buffers}}
    wal_log_hints: 'on'
  recovery_conf:
    restore_command: envdir "{{WALE_ENV_DIR}}" wal-e --aws-instance-profile wal-fetch "%f" "%p" -p 1
'''


def get_instance_meta_data(key):
    try:
        result = requests.get('http://instance-data/latest/meta-data/{}'.format(key), timeout=2)
        if result.status_code != 200:
            raise Exception('Received status code {} ({})'.format(result.status_code, result.text))
        return result.text
    except Exception, e:
        logging.debug('Could not inspect instance metadata for key {}, error: {}'.format(key, e))


def get_placeholders():
    placeholders = dict(os.environ)

    placeholders.setdefault('PGHOME', os.path.expanduser('~'))
    placeholders.setdefault('APIPORT', '8008')
    placeholders.setdefault('BACKUP_SCHEDULE', '00 01 * * *')
    placeholders.setdefault('CRONTAB', '[]')
    placeholders.setdefault('PGDATA', os.path.join(placeholders['PGHOME'], 'pgdata'))
    placeholders.setdefault('PGPASSWORD_ADMIN', 'standby')
    placeholders.setdefault('PGPASSWORD_STANDBY', 'standby')
    placeholders.setdefault('PGPASSWORD_SUPERUSER', 'zalando')
    placeholders.setdefault('PGPORT', '5432')
    placeholders.setdefault('SCOPE', 'dummy')
    placeholders.setdefault('SSL_CERTIFICATE_FILE', os.path.join(placeholders['PGHOME'], 'server.crt'))
    placeholders.setdefault('SSL_PRIVATE_KEY_FILE', os.path.join(placeholders['PGHOME'], 'server.key'))
    placeholders.setdefault('WALE_BACKUP_THRESHOLD_MEGABYTES', 1024)
    placeholders.setdefault('WALE_BACKUP_THRESHOLD_PERCENTAGE', 30)
    placeholders.setdefault('WALE_ENV_DIR', os.path.join(placeholders['PGHOME'], 'etc', 'wal-e.d', 'env'))
    placeholders.setdefault('WAL_S3_BUCKET', 'spilo-example-com')

    placeholders.setdefault('postgresql', {})
    placeholders['postgresql'].setdefault('parameters', {})

    os_memory_mb = os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES') / 1024 / 1024

    # # We take 1/4 of the memory, expressed in full MB's
    placeholders['postgresql']['parameters']['shared_buffers'] = '{}MB'.format(int(os_memory_mb/4))
    # # 1 connection per 30 MB, at least 100
    placeholders['postgresql']['parameters']['max_connections'] = max(100, int(os_memory_mb/30))

    placeholders['instance_data'] = dict()
    placeholders['instance_data']['ip'] = get_instance_meta_data('local-ipv4') \
        or socket.gethostbyname(socket.gethostname())
    placeholders['instance_data']['id'] = re.sub(r'\W+', '_', get_instance_meta_data('instance-id')
                                                 or socket.gethostname())

    return placeholders


def write_configuration(config, filename):
    with open(filename, 'w') as f:
        f.write(yaml.dump(config, default_flow_style=False, width=120))


def pystache_render(*args, **kwargs):
    render = pystache.Renderer(missing_tags='strict')
    return render.render(*args, **kwargs)


def get_dcs_config(config, placeholders):
    defaults = \
        yaml.load('''\
zookeeper:
  scope: {scope}
  session_timeout: {ttl}
  reconnect_timeout: {loop_wait}
etcd:
  scope: {scope}
  ttl: {ttl}'''.format(**config))

    config = {}

    if 'ZOOKEEPER_HOSTS' in placeholders:
        config = {'zookeeper': defaults['zookeeper']}
        config['zookeeper']['hosts'] = yaml.load(placeholders['ZOOKEEPER_HOSTS'])
    elif 'EXHIBITOR_HOSTS' in placeholders and 'EXHIBITOR_PORT' in placeholders:
        config = {'zookeeper': defaults['zookeeper']}
        config['zookeeper']['exhibitor'] = {'poll_interval': '300', 'port': placeholders['EXHIBITOR_PORT'],
                                            'hosts': yaml.load(placeholders['EXHIBITOR_HOSTS'])}
    elif 'ETCD_HOST' in placeholders:
        config = {'etcd': defaults['etcd']}
        config['etcd']['host'] = placeholders['ETCD_HOST']
    elif 'ETCD_DISCOVERY_DOMAIN' in placeholders:
        config = {'etcd': defaults['etcd']}
        config['etcd']['discovery_srv'] = placeholders['ETCD_DISCOVERY_DOMAIN']
    else:
        pass  # Configuration can also be specified using PATRONI_CONFIGURATION

    return config


def write_wale_command_environment(placeholders):
    az = get_instance_meta_data('placement/availability-zone') or 'dummy-region'

    if not os.path.exists(placeholders['WALE_ENV_DIR']):
        os.makedirs(placeholders['WALE_ENV_DIR'])

    with open(os.path.join(placeholders['WALE_ENV_DIR'], 'WALE_S3_PREFIX'), 'w') as f:
        f.write('s3://{WAL_S3_BUCKET}/spilo/{SCOPE}/wal/'.format(**placeholders))

    with open(os.path.join(placeholders['WALE_ENV_DIR'], 'WALE_S3_ENDPOINT'), 'w') as f:
        f.write('https+path://s3-{}.amazonaws.com:443'.format(az[:-1]))


def write_crontab(placeholders, path):
    lines = ['PATH={}'.format(path)]
    lines += ['{BACKUP_SCHEDULE} /postgres_backup.sh "{WALE_ENV_DIR}" "{PGDATA}"'.format(**placeholders)]
    lines += yaml.load(placeholders['CRONTAB'])
    lines += ['']  # EOF requires empty line for cron

    c = subprocess.Popen(['crontab'], stdin=subprocess.PIPE)
    c.communicate(input='\n'.join(lines).encode())


def configure_patronictl(patroni_configfile, patronictl_configfile):
    if not os.path.exists(os.path.dirname(patronictl_configfile)):
        os.makedirs(os.path.dirname(patronictl_configfile))
    if not os.path.exists(patronictl_configfile):
        os.symlink(patroni_configfile, patronictl_configfile)


def main():
    debug = os.environ.get('DEBUG', '') in ['1', 'true', 'on', 'ON']
    logging.basicConfig(format='%(asctime)s - bootstrapping - %(levelname)s - %(message)s', level=('DEBUG'
                         if debug else 'INFO'))
    if debug:
        logging.warning('variable DEBUG was set, dropping you to a bash shell. (unset DEBUG to avoid this)')
        os.execlpe('bash', 'bash', dict(os.environ))

    placeholders = get_placeholders()

    write_certificates(placeholders)

    config = yaml.load(pystache_render(TEMPLATE, placeholders))
    config.update(get_dcs_config(config, placeholders))

    user_config = yaml.load(os.environ.get('PATRONI_CONFIGURATION', '')) or {}
    if not isinstance(user_config, dict):
        raise ValueError('PATRONI_CONFIGURATION should contain a dict, yet it is a {}'.format(type(user_config)))

    config = deep_update(user_config, config)

    # Ensure replication is available
    if not any(['replication' in i for i in config['postgresql']['pg_hba']]):
        rep_hba = 'hostssl replication {} 0.0.0.0/0 md5'.format(config['postgresql']['replication']['username'])
        config['postgresql']['pg_hba'].insert(0, rep_hba)

    # Patroni configuration
    patroni_configfile = os.path.join(placeholders['PGHOME'], 'postgres.yml')
    write_configuration(config, patroni_configfile)

    configure_patronictl(patroni_configfile, os.path.join(placeholders['PGHOME'], '.config', 'patroni',
                         'patronictl.yaml'))

    # WAL-E
    write_wale_command_environment(placeholders)

    # # We run cron, to schedule recurring tasks on the node
    logging.info('Starting up cron')
    write_crontab(placeholders, os.environ.get('PATH'))
    subprocess.call(['/usr/bin/sudo', '/usr/sbin/cron'])

    # # We run 1 backup, with INITIAL_BACKUP set
    subprocess.Popen(['/bin/bash', '/postgres_backup.sh', placeholders['WALE_ENV_DIR'], placeholders['PGDATA']],
                     env={'PATH': os.environ['PATH'], 'INITIAL_BACKUP': '1'})

    os.execlpe('patroni', 'patroni', patroni_configfile, {'PATH': os.environ.get('PATH')})


if __name__ == '__main__':
    main()
