#!/usr/bin/env python
# -*- coding: utf-8 -*-

import argparse
import logging
import re
import os
import socket
import subprocess

from six.moves.urllib_parse import urlparse

import yaml
import pystache
import requests


def parse_args():
    sections = ['all', 'patroni', 'patronictl', 'certificate', 'wal-e', 'crontab', 'ldap']
    argp = argparse.ArgumentParser(description='Configures Spilo',
                                   epilog="Choose from the following sections:\n\t{}".format('\n\t'.join(sections)),
                                   formatter_class=argparse.RawDescriptionHelpFormatter)

    argp.add_argument('sections', metavar='sections', type=str, nargs='+', choices=sections,
                      help='Which section to (re)configure')
    argp.add_argument('-l', '--loglevel', type=str, help='Explicitly set loglevel')
    argp.add_argument('-f', '--force', help='Overwrite files if they exist', default=False, action='store_true')

    args = vars(argp.parse_args())

    if 'all' in args['sections']:
        args['sections'] = sections
        args['sections'].remove('all')
    args['sections'] = set(args['sections'])

    return args


def write_certificates(environment, overwrite):
    """Write SSL certificate to files

    If certificates are specified, they are written, otherwise
    dummy certificates are generated and written"""

    ssl_keys = ['SSL_CERTIFICATE', 'SSL_PRIVATE_KEY']
    if set(ssl_keys) <= set(environment):
        for k in ssl_keys:
            write_file(environment[k], environment[k + '_FILE'], overwrite)
    else:
        if os.path.exists(environment['SSL_PRIVATE_KEY_FILE']) and not overwrite:
            logging.warning('Private key already exists, not overwriting. (Use option --force if necessary)')
            return
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

    uid = os.stat(environment['PGHOME']).st_uid
    os.chmod(environment['SSL_PRIVATE_KEY_FILE'], 0o600)
    os.chown(environment['SSL_PRIVATE_KEY_FILE'], uid, -1)


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
    log_line_prefix: '%t [%p]: [%l-1] %c %x %d %u %a %h '
    log_checkpoints: 'on'
    log_lock_waits: 'on'
    log_min_duration_statement: 500
    log_autovacuum_min_duration: 0
    log_connections: 'on'
    log_disconnections: 'on'
    log_statement: 'ddl'
    log_temp_files: 0
  recovery_conf:
    restore_command: envdir "{{WALE_ENV_DIR}}" wal-e --aws-instance-profile wal-fetch "%f" "%p" -p 1
'''


def get_instance_meta_data(key):
    try:
        result = requests.get('http://instance-data/latest/meta-data/{}'.format(key), timeout=2)
        if result.status_code != 200:
            raise Exception('Received status code {} ({})'.format(result.status_code, result.text))
        return result.text
    except Exception as e:
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
    # # 1 connection per 30 MB, at least 100, at most 1000
    placeholders['postgresql']['parameters']['max_connections'] = min(max(100, int(os_memory_mb/30)), 1000)

    placeholders['instance_data'] = dict()
    placeholders['instance_data']['ip'] = get_instance_meta_data('local-ipv4') \
        or socket.gethostbyname(socket.gethostname())
    placeholders['instance_data']['id'] = re.sub(r'\W+', '_', get_instance_meta_data('instance-id')
                                                 or socket.gethostname())

    return placeholders


def write_file(config, filename, overwrite):
    if not overwrite and os.path.exists(filename):
        logging.warning('File {} already exists, not overwriting. (Use option --force if necessary)'.format(filename))
    with open(filename, 'w') as f:
        logging.info('Writing to file {}'.format(filename))
        f.write(config)


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


def write_wale_command_environment(placeholders, overwrite):
    az = get_instance_meta_data('placement/availability-zone') or 'dummy-region'

    if not os.path.exists(placeholders['WALE_ENV_DIR']):
        os.makedirs(placeholders['WALE_ENV_DIR'])

    write_file('s3://{WAL_S3_BUCKET}/spilo/{SCOPE}/wal/'.format(**placeholders),
               os.path.join(placeholders['WALE_ENV_DIR'], 'WALE_S3_PREFIX'), overwrite)
    write_file('https+path://s3-{}.amazonaws.com:443'.format(az[:-1]),
               os.path.join(placeholders['WALE_ENV_DIR'], 'WALE_S3_ENDPOINT'), overwrite)


def write_crontab(placeholders, path, overwrite):

    if not overwrite:
        with open(os.devnull, 'w') as devnull:
            cron_exit = subprocess.call(['sudo', '-u', 'postgres', 'crontab', '-l'], stdout=devnull, stderr=devnull)
            if cron_exit == 0:
                logging.warning('Cron is already configured. (Use option --force to overwrite cron)')
                return

    lines = ['PATH={}'.format(path)]
    lines += ['{BACKUP_SCHEDULE} /postgres_backup.sh "{WALE_ENV_DIR}" "{PGDATA}"'.format(**placeholders)]
    lines += yaml.load(placeholders['CRONTAB'])
    lines += ['']  # EOF requires empty line for cron

    c = subprocess.Popen(['sudo', '-u', 'postgres', 'crontab'], stdin=subprocess.PIPE)
    c.communicate(input='\n'.join(lines).encode())


def write_ldap_configuration(placeholders, overwrite):
    if not 'LDAP_URL' in placeholders:
        logging.info("No LDAP_URL was specified, skipping LDAP configuration")
        return

    r = urlparse(placeholders['LDAP_URL'])
    if not r.scheme:
        logging.error('LDAP_URL should contain a scheme')
        logging.info(r)
        return

    host, port = r.hostname, r.port
    if not port:
        port = 636 if r.scheme == 'ldaps' else '389'

    stunnel_config = """\
foreground = yes
options = NO_SSLv2

[ldaps]
connect = {0}:{1}
client = yes
accept = 389
verify = 3
CAfile = /etc/stunnel/chain.pem
""".format(host, port)
    write_file(stunnel_config, '/etc/stunnel/ldap.conf', overwrite)

    supervisord_config = """\
[program:ldaptunnel]
autostart=true
priority=500
directory=/
command=env -i /usr/bin/stunnel4 /etc/stunnel/ldap.conf
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
redirect_stderr=true
"""
    write_file(supervisord_config, '/etc/supervisor/conf.d/ldaptunnel.conf', overwrite)


def main():
    debug = os.environ.get('DEBUG', '') in ['1', 'true', 'on', 'ON']
    args = parse_args()

    logging.basicConfig(format='%(asctime)s - bootstrapping - %(levelname)s - %(message)s', level=('DEBUG'
                         if debug else (args.get('loglevel') or 'INFO').upper()))

    placeholders = get_placeholders()

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

    for section in args['sections']:
        logging.info('Configuring {}'.format(section))
        if section == 'patroni':
            patroni_configfile = os.path.join(placeholders['PGHOME'], 'postgres.yml')
            write_file(yaml.dump(config, default_flow_style=False, width=120), patroni_configfile, args['force'])
        elif section == 'patronictl':
            patronictl_config = {k: v for k, v in config.items() if k in ['zookeeper', 'etcd', 'consul']}
            patronictl_configfile = os.path.join(placeholders['PGHOME'], '.config', 'patroni', 'patronictl.yaml')
            if not os.path.exists(os.path.dirname(patronictl_configfile)):
                os.makedirs(os.path.dirname(patronictl_configfile))
            write_file(yaml.dump(patronictl_config), patronictl_configfile, args['force'])
        elif section == 'wal-e':
            write_wale_command_environment(placeholders, args['force'])
        elif section == 'certificate':
            write_certificates(placeholders, args['force'])
        elif section == 'crontab':
            write_crontab(placeholders, os.environ.get('PATH'), args['force'])
        elif section == 'ldap':
            write_ldap_configuration(placeholders, args['force'])
        else:
            raise Exception('Unknown section: {}'.format(section))


if __name__ == '__main__':
    main()
