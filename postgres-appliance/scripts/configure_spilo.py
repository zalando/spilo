#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import logging
import re
import os
import psutil
import socket
import subprocess
import sys

from copy import deepcopy
from six.moves.urllib_parse import urlparse
from collections import defaultdict

import yaml
import pystache
import requests

PROVIDER_AZURE = "azure"
PROVIDER_AWS = "aws"
PROVIDER_GOOGLE = "google"
PROVIDER_OPENSTACK = "openstack"
PROVIDER_LOCAL = "local"
PROVIDER_UNSUPPORTED = "unsupported"
USE_KUBERNETES = os.environ.get('KUBERNETES_SERVICE_HOST') is not None
KUBERNETES_DEFAULT_LABELS = '{"application": "spilo"}'
MEMORY_LIMIT_IN_BYTES_PATH = '/sys/fs/cgroup/memory/memory.limit_in_bytes'


# (min_version, max_version, shared_preload_libraries, extwlist.extensions)
extensions = {
    'timescaledb':    (9.6, 11, True,  True),
    'pg_cron':        (9.5, 12, True,  False),
    'pg_stat_kcache': (9.4, 12, True,  False),
    'pg_partman':     (9.4, 12, False, True)
}

AUTO_ENABLE_WALG_RESTORE = ('WAL_S3_BUCKET', 'WALE_S3_PREFIX', 'WALG_S3_PREFIX')


def parse_args():
    sections = ['all', 'patroni', 'patronictl', 'pgqd', 'certificate', 'wal-e', 'crontab',
                'pam-oauth2', 'pgbouncer', 'bootstrap', 'standby-cluster', 'log', 'renice']
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


def link_runit_service(name):
    service_dir = '/run/service/' + name
    if not os.path.exists(service_dir):
        os.makedirs(service_dir)
        run_file = service_dir + '/run'
        if not os.path.exists(run_file):
            source_file = '/etc/runit/runsvdir/default/{0}/run'.format(name)
            os.symlink(source_file, run_file)


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
bootstrap:
  post_init: /scripts/post_init.sh "{{HUMAN_ROLE}}"
  dcs:
    {{#STANDBY_CLUSTER}}
    standby_cluster:
      create_replica_methods:
      {{#STANDBY_WITH_WALE}}
      - bootstrap_standby_with_wale
      {{/STANDBY_WITH_WALE}}
      - basebackup_fast_xlog
      {{#STANDBY_WITH_WALE}}
      restore_command: envdir "{{STANDBY_WALE_ENV_DIR}}" /scripts/restore_command.sh "%f" "%p"
      {{/STANDBY_WITH_WALE}}
      {{#STANDBY_HOST}}
      host: {{STANDBY_HOST}}
      {{/STANDBY_HOST}}
      {{#STANDBY_PORT}}
      port: {{STANDBY_PORT}}
      {{/STANDBY_PORT}}
    {{/STANDBY_CLUSTER}}
    ttl: 30
    loop_wait: &loop_wait 10
    retry_timeout: 10
    maximum_lag_on_failover: 33554432
    postgresql:
      use_pg_rewind: true
      use_slots: true
      parameters:
        archive_mode: "on"
        archive_timeout: 1800s
        wal_level: hot_standby
        wal_keep_segments: 8
        wal_log_hints: 'on'
        max_wal_senders: 10
        max_connections: {{postgresql.parameters.max_connections}}
        max_replication_slots: 10
        hot_standby: 'on'
        tcp_keepalives_idle: 900
        tcp_keepalives_interval: 100
        log_line_prefix: '%t [%p]: [%l-1] %c %x %d %u %a %h '
        log_checkpoints: 'on'
        log_lock_waits: 'on'
        log_min_duration_statement: 500
        log_autovacuum_min_duration: 0
        log_connections: 'on'
        log_disconnections: 'on'
        log_statement: 'ddl'
        log_temp_files: 0
        track_functions: all
        checkpoint_completion_target: 0.9
        autovacuum_max_workers: 5
        autovacuum_vacuum_scale_factor: 0.05
        autovacuum_analyze_scale_factor: 0.02
  {{#CLONE_WITH_WALE}}
  method: clone_with_wale
  clone_with_wale:
    command: envdir "{{CLONE_WALE_ENV_DIR}}" python3 /scripts/clone_with_wale.py --recovery-target-time="{{CLONE_TARGET_TIME}}"
    recovery_conf:
        restore_command: envdir "{{CLONE_WALE_ENV_DIR}}" /scripts/restore_command.sh "%f" "%p"
        recovery_target_timeline: latest
        {{#USE_PAUSE_AT_RECOVERY_TARGET}}
        recovery_target_action: pause
        {{/USE_PAUSE_AT_RECOVERY_TARGET}}
        {{^USE_PAUSE_AT_RECOVERY_TARGET}}
        recovery_target_action: promote
        {{/USE_PAUSE_AT_RECOVERY_TARGET}}
        {{#CLONE_TARGET_TIME}}
        recovery_target_time: "{{CLONE_TARGET_TIME}}"
        {{/CLONE_TARGET_TIME}}
        {{^CLONE_TARGET_INCLUSIVE}}
        recovery_target_inclusive: false
        {{/CLONE_TARGET_INCLUSIVE}}
  {{/CLONE_WITH_WALE}}
  {{#CLONE_WITH_BASEBACKUP}}
  method: clone_with_basebackup
  clone_with_basebackup:
    command: python3 /scripts/clone_with_basebackup.py --pgpass={{CLONE_PGPASS}} --host={{CLONE_HOST}} --port={{CLONE_PORT}} --user="{{CLONE_USER}}"
  {{/CLONE_WITH_BASEBACKUP}}
  initdb:
    - encoding: UTF8
    - locale: en_US.UTF-8
    - data-checksums
  {{#USE_ADMIN}}
  users:
    {{PGUSER_ADMIN}}:
      password: {{PGPASSWORD_ADMIN}}
      options:
        - createrole
        - createdb
  {{/USE_ADMIN}}
scope: &scope '{{SCOPE}}'
restapi:
  listen: ':{{APIPORT}}'
  connect_address: {{instance_data.ip}}:{{APIPORT}}
postgresql:
  use_unix_socket: true
  name: '{{instance_data.id}}'
  listen: '*:{{PGPORT}}'
  connect_address: {{instance_data.ip}}:{{PGPORT}}
  data_dir: {{PGDATA}}
  parameters:
    archive_command: {{{postgresql.parameters.archive_command}}}
    shared_buffers: {{postgresql.parameters.shared_buffers}}
    logging_collector: 'on'
    log_destination: csvlog
    log_directory: ../pg_log
    log_filename: 'postgresql-%u.log'
    log_file_mode: '0644'
    log_rotation_age: '1d'
    log_truncate_on_rotation: 'on'
    ssl: 'on'
    {{#SSL_CA_FILE}}
    ssl_ca_file: {{SSL_CA_FILE}}
    {{/SSL_CA_FILE}}
    {{#SSL_CRL_FILE}}
    ssl_crl_file: {{SSL_CRL_FILE}}
    {{/SSL_CRL_FILE}}
    ssl_cert_file: {{SSL_CERTIFICATE_FILE}}
    ssl_key_file: {{SSL_PRIVATE_KEY_FILE}}
    shared_preload_libraries: 'bg_mon,pg_stat_statements,pgextwlist,pg_auth_mon,set_user'
    bg_mon.listen_address: '{{BGMON_LISTEN_IP}}'
    pg_stat_statements.track_utility: 'off'
    extwlist.extensions: 'btree_gin,btree_gist,citext,hstore,intarray,ltree,pgcrypto,pgq,pg_trgm,postgres_fdw,uuid-ossp,hypopg'
    extwlist.custom_path: /scripts
  pg_hba:
    - local   all             all                                   trust
    {{#PAM_OAUTH2}}
    - hostssl all             +{{HUMAN_ROLE}}    127.0.0.1/32       pam
    {{/PAM_OAUTH2}}
    - host    all             all                127.0.0.1/32       md5
    {{#PAM_OAUTH2}}
    - hostssl all             +{{HUMAN_ROLE}}    ::1/128            pam
    {{/PAM_OAUTH2}}
    - host    all             all                ::1/128            md5
    - hostssl replication     {{PGUSER_STANDBY}} all                md5
    {{^ALLOW_NOSSL}}
    - hostnossl all           all                all                reject
    {{/ALLOW_NOSSL}}
    {{#PAM_OAUTH2}}
    - hostssl all             +{{HUMAN_ROLE}}    all                pam
    {{/PAM_OAUTH2}}
    {{#ALLOW_NOSSL}}
    - host    all             all                all                md5
    {{/ALLOW_NOSSL}}
    {{^ALLOW_NOSSL}}
    - hostssl all             all                all                md5
    {{/ALLOW_NOSSL}}

  {{#USE_WALE}}
  recovery_conf:
    restore_command: envdir "{{WALE_ENV_DIR}}" /scripts/restore_command.sh "%f" "%p"
  {{/USE_WALE}}
  authentication:
    superuser:
      username: {{PGUSER_SUPERUSER}}
      password: '{{PGPASSWORD_SUPERUSER}}'
    replication:
      username: {{PGUSER_STANDBY}}
      password: '{{PGPASSWORD_STANDBY}}'
  callbacks:
  {{#CALLBACK_SCRIPT}}
    on_start: {{CALLBACK_SCRIPT}}
    on_stop: {{CALLBACK_SCRIPT}}
    on_role_change: '/scripts/on_role_change.sh {{HUMAN_ROLE}} {{CALLBACK_SCRIPT}}'
 {{/CALLBACK_SCRIPT}}
 {{^CALLBACK_SCRIPT}}
    on_role_change: '/scripts/on_role_change.sh {{HUMAN_ROLE}} true'
 {{/CALLBACK_SCRIPT}}
{{#USE_WALE}}
  create_replica_method:
    - wal_e
    - basebackup_fast_xlog
  wal_e:
    command: envdir {{WALE_ENV_DIR}} bash /scripts/wale_restore.sh
    threshold_megabytes: {{WALE_BACKUP_THRESHOLD_MEGABYTES}}
    threshold_backup_size_percentage: {{WALE_BACKUP_THRESHOLD_PERCENTAGE}}
    retries: 2
    no_master: 1
  basebackup_fast_xlog:
    command: /scripts/basebackup.sh
    retries: 2
{{/USE_WALE}}
{{#STANDBY_WITH_WALE}}
  bootstrap_standby_with_wale:
    command: envdir "{{STANDBY_WALE_ENV_DIR}}" bash /scripts/wale_restore.sh
    threshold_megabytes: {{WALE_BACKUP_THRESHOLD_MEGABYTES}}
    threshold_backup_size_percentage: {{WALE_BACKUP_THRESHOLD_PERCENTAGE}}
    retries: 2
    no_master: 1
{{/STANDBY_WITH_WALE}}
'''


def get_provider():
    provider = os.environ.get('SPILO_PROVIDER')
    if provider:
        if provider in {PROVIDER_AZURE, PROVIDER_AWS, PROVIDER_GOOGLE, PROVIDER_OPENSTACK, PROVIDER_LOCAL}:
            return provider
        else:
            logging.error('Unknown SPILO_PROVIDER: %s', provider)
            return PROVIDER_UNSUPPORTED

    if os.environ.get('DEVELOP', '').lower() in ['1', 'true', 'on']:
        return PROVIDER_LOCAL

    try:
        logging.info("Figuring out my environment (Google? Azure? AWS? Openstack? Local?)")
        r = requests.get('http://169.254.169.254', timeout=2)
        if r.headers.get('Metadata-Flavor', '') == 'Google':
            return PROVIDER_GOOGLE
        else:
            # accessible on Openstack, will fail on AWS
            r = requests.get('http://169.254.169.254/openstack/latest/meta_data.json')
            if r.ok:
                return PROVIDER_OPENSTACK

            # is accessible from both AWS and Openstack, Possiblity of misidentification if previous try fails
            r = requests.get('http://169.254.169.254/latest/meta-data/ami-id')
            return PROVIDER_AWS if r.ok else PROVIDER_UNSUPPORTED
    except (requests.exceptions.ConnectTimeout, requests.exceptions.ConnectionError, requests.exceptions.ReadTimeout):
        logging.info("Could not connect to 169.254.169.254, assuming local Docker setup")
        return PROVIDER_LOCAL


def get_instance_metadata(provider):
    metadata = {'ip': socket.getaddrinfo(socket.gethostname(), 0, socket.AF_UNSPEC, socket.SOCK_STREAM, 0)[0][4][0],
                'id': socket.gethostname(),
                'zone': 'local'}

    if USE_KUBERNETES:
        metadata['ip'] = os.environ.get('POD_IP', metadata['ip'])

    headers = {}
    if provider == PROVIDER_GOOGLE:
        headers['Metadata-Flavor'] = 'Google'
        url = 'http://metadata.google.internal/computeMetadata/v1/instance'
        mapping = {'zone': 'zone'}
        if not USE_KUBERNETES:
            mapping.update({'id': 'id'})
    elif provider == PROVIDER_AWS or provider == PROVIDER_OPENSTACK or provider == PROVIDER_AZURE:
        url = 'http://169.254.169.254/latest/meta-data'
        mapping = {'zone': 'placement/availability-zone'}
        if not USE_KUBERNETES:
            mapping.update({'ip': 'local-ipv4', 'id': 'instance-id'})
    else:
        logging.info("No meta-data available for this provider")
        return metadata

    for k, v in mapping.items():
        metadata[k] = requests.get('{}/{}'.format(url, v or k), timeout=2, headers=headers).text

    return metadata


def set_extended_wale_placeholders(placeholders, prefix):
    """ checks that enough parameters are provided to configure cloning or standby with WAL-E """
    for name in ('S3', 'GS', 'GCS', 'SWIFT'):
        if placeholders.get('{0}WALE_{1}_PREFIX'.format(prefix, name)) or\
                name in ('S3', 'GS') and placeholders.get('{0}WALG_{1}_PREFIX'.format(prefix, name)) or\
                placeholders.get('{0}WAL_{1}_BUCKET'.format(prefix, name)) and placeholders.get(prefix + 'SCOPE'):
            break
    else:
        return False

    scope = placeholders.get(prefix + 'SCOPE')
    dirname = 'env-' + prefix[:-1].lower() + ('-' + scope if scope else '')
    placeholders[prefix + 'WALE_ENV_DIR'] = os.path.join(placeholders['PGHOME'], 'etc', 'wal-e.d', dirname)
    placeholders[prefix + 'WITH_WALE'] = True
    return name


def set_walg_placeholders(placeholders, prefix=''):
    walg_supported = any(placeholders.get(prefix + n) for n in AUTO_ENABLE_WALG_RESTORE +
                         ('WAL_GS_BUCKET', 'WALE_GS_PREFIX', 'WALG_GS_PREFIX'))
    default = placeholders.get('USE_WALG', False)
    placeholders.setdefault(prefix + 'USE_WALG', default)
    for name in ('USE_WALG_BACKUP', 'USE_WALG_RESTORE'):
        value = str(placeholders.get(prefix + name, placeholders[prefix + 'USE_WALG'])).lower()
        placeholders[prefix + name] = 'true' if value == 'true' and walg_supported else None


def get_listen_ip():
    """ Get IP to listen on for things that don't natively support detecting IPv4/IPv6 dualstack """
    def has_dual_stack():
        if hasattr(socket, 'AF_INET6') and hasattr(socket, 'IPPROTO_IPV6') and hasattr(socket, 'IPV6_V6ONLY'):
            sock = None
            try:
                sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
                sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, False)
                import urllib3
                return urllib3.util.connection.HAS_IPV6
            except socket.error as e:
                logging.debug('Error when working with ipv6 socket: %s', e)
            finally:
                if sock:
                    sock.close()
        return False

    info = socket.getaddrinfo(None, 0, socket.AF_UNSPEC, socket.SOCK_STREAM, 0, socket.AI_PASSIVE)
    # in case dual stack is not supported we want IPv4 to be preferred over IPv6
    info.sort(key=lambda x: x[0] == socket.AF_INET, reverse=not has_dual_stack())
    return info[0][4][0]


def get_placeholders(provider):
    placeholders = dict(os.environ)

    placeholders.setdefault('PGHOME', os.path.expanduser('~'))
    placeholders.setdefault('APIPORT', '8008')
    placeholders.setdefault('BACKUP_SCHEDULE', '0 1 * * *')
    placeholders.setdefault('BACKUP_NUM_TO_RETAIN', 2)
    placeholders.setdefault('CRONTAB', '[]')
    placeholders.setdefault('PGROOT', os.path.join(placeholders['PGHOME'], 'pgroot'))
    placeholders.setdefault('WALE_TMPDIR', os.path.abspath(os.path.join(placeholders['PGROOT'], '../tmp')))
    placeholders.setdefault('PGDATA', os.path.join(placeholders['PGROOT'], 'pgdata'))
    placeholders.setdefault('HUMAN_ROLE', 'zalandos')
    placeholders.setdefault('PGUSER_STANDBY', 'standby')
    placeholders.setdefault('PGPASSWORD_STANDBY', 'standby')
    placeholders.setdefault('USE_ADMIN', 'PGPASSWORD_ADMIN' in placeholders)
    placeholders.setdefault('PGUSER_ADMIN', 'admin')
    placeholders.setdefault('PGPASSWORD_ADMIN', 'cola')
    placeholders.setdefault('PGUSER_SUPERUSER', 'postgres')
    placeholders.setdefault('PGPASSWORD_SUPERUSER', 'zalando')
    placeholders.setdefault('ALLOW_NOSSL', '')
    placeholders.setdefault('BGMON_LISTEN_IP', '0.0.0.0')
    placeholders.setdefault('PGPORT', '5432')
    placeholders.setdefault('SCOPE', 'dummy')
    placeholders.setdefault('SSL_TEST_RELOAD', 'SSL_PRIVATE_KEY_FILE' in os.environ)
    placeholders.setdefault('SSL_CA_FILE', '')
    placeholders.setdefault('SSL_CRL_FILE', '')
    placeholders.setdefault('SSL_CERTIFICATE_FILE', os.path.join(placeholders['PGHOME'], 'server.crt'))
    placeholders.setdefault('SSL_PRIVATE_KEY_FILE', os.path.join(placeholders['PGHOME'], 'server.key'))
    placeholders.setdefault('WALE_BACKUP_THRESHOLD_MEGABYTES', 102400)
    placeholders.setdefault('WALE_BACKUP_THRESHOLD_PERCENTAGE', 30)
    # if Kubernetes is defined as a DCS, derive the namespace from the POD_NAMESPACE, if not set explicitely.
    # We only do this for Kubernetes DCS, as we don't want to suddently change, i.e. DCS base path when running
    # in Kubernetes with Etcd in a non-default namespace
    placeholders.setdefault('NAMESPACE', placeholders.get('POD_NAMESPACE', 'default')
                            if USE_KUBERNETES and placeholders.get('DCS_ENABLE_KUBERNETES_API') else '')
    # use namespaces to set WAL bucket prefix scope naming the folder namespace-clustername for non-default namespace.
    placeholders.setdefault('WAL_BUCKET_SCOPE_PREFIX', '{0}-'.format(placeholders['NAMESPACE'])
                            if placeholders['NAMESPACE'] not in ('default', '') else '')
    placeholders.setdefault('WAL_BUCKET_SCOPE_SUFFIX', '')
    placeholders.setdefault('WALE_ENV_DIR', os.path.join(placeholders['PGHOME'], 'etc', 'wal-e.d', 'env'))
    placeholders.setdefault('USE_WALE', False)
    cpu_count = str(min(psutil.cpu_count(), 10))
    placeholders.setdefault('WALG_DOWNLOAD_CONCURRENCY', cpu_count)
    placeholders.setdefault('WALG_UPLOAD_CONCURRENCY', cpu_count)
    placeholders.setdefault('PAM_OAUTH2', '')
    placeholders.setdefault('CALLBACK_SCRIPT', '')
    placeholders.setdefault('DCS_ENABLE_KUBERNETES_API', '')
    placeholders.setdefault('KUBERNETES_ROLE_LABEL', 'spilo-role')
    placeholders.setdefault('KUBERNETES_SCOPE_LABEL', 'version')
    placeholders.setdefault('KUBERNETES_LABELS', KUBERNETES_DEFAULT_LABELS)
    placeholders.setdefault('KUBERNETES_USE_CONFIGMAPS', '')
    placeholders.setdefault('USE_PAUSE_AT_RECOVERY_TARGET', False)
    placeholders.setdefault('CLONE_METHOD', '')
    placeholders.setdefault('CLONE_WITH_WALE', '')
    placeholders.setdefault('CLONE_WITH_BASEBACKUP', '')
    placeholders.setdefault('CLONE_TARGET_TIME', '')
    placeholders.setdefault('CLONE_TARGET_INCLUSIVE', True)

    placeholders.setdefault('LOG_SHIP_SCHEDULE', '1 0 * * *')
    placeholders.setdefault('LOG_S3_BUCKET', '')
    placeholders.setdefault('LOG_TMPDIR', os.path.abspath(os.path.join(placeholders['PGROOT'], '../tmp')))
    placeholders.setdefault('LOG_BUCKET_SCOPE_SUFFIX', '')

    # see comment for wal-e bucket prefix
    placeholders.setdefault('LOG_BUCKET_SCOPE_PREFIX', '{0}-'.format(placeholders['NAMESPACE'])
                            if placeholders['NAMESPACE'] not in ('default', '') else '')

    if placeholders['CLONE_METHOD'] == 'CLONE_WITH_WALE':
        # modify placeholders and take care of error cases
        name = set_extended_wale_placeholders(placeholders, 'CLONE_')
        if name is False:
            logging.warning('Cloning with WAL-E is only possible when CLONE_WALE_*_PREFIX '
                            'or CLONE_WALG_*_PREFIX or CLONE_WAL_*_BUCKET and CLONE_SCOPE are set.')
        elif name == 'S3':
            placeholders.setdefault('CLONE_USE_WALG', 'true')
    elif placeholders['CLONE_METHOD'] == 'CLONE_WITH_BASEBACKUP':
        clone_scope = placeholders.get('CLONE_SCOPE')
        if clone_scope and placeholders.get('CLONE_HOST') \
                and placeholders.get('CLONE_USER') and placeholders.get('CLONE_PASSWORD'):
            placeholders['CLONE_WITH_BASEBACKUP'] = True
            placeholders.setdefault('CLONE_PGPASS', os.path.join(placeholders['PGHOME'],
                                                                 '.pgpass_{0}'.format(clone_scope)))
            placeholders.setdefault('CLONE_PORT', 5432)
        else:
            logging.warning("Clone method is set to basebackup, but no 'CLONE_SCOPE' "
                            "or 'CLONE_HOST' or 'CLONE_USER' or 'CLONE_PASSWORD' specified")
    else:
        if set_extended_wale_placeholders(placeholders, 'STANDBY_') == 'S3':
            placeholders.setdefault('STANDBY_USE_WALG', 'true')

    placeholders.setdefault('STANDBY_WITH_WALE', '')
    placeholders.setdefault('STANDBY_HOST', '')
    placeholders.setdefault('STANDBY_PORT', '')
    placeholders.setdefault('STANDBY_CLUSTER', placeholders['STANDBY_WITH_WALE'] or placeholders['STANDBY_HOST'])

    if provider == PROVIDER_AWS and not USE_KUBERNETES:
        # AWS specific callback to tag the instances with roles
        placeholders['CALLBACK_SCRIPT'] = 'python3 /scripts/callback_aws.py'
        if placeholders.get('EIP_ALLOCATION'):
            placeholders['CALLBACK_SCRIPT'] += ' ' + placeholders['EIP_ALLOCATION']

    if any(placeholders.get(n) for n in AUTO_ENABLE_WALG_RESTORE):
        placeholders.setdefault('USE_WALG_RESTORE', 'true')
    set_walg_placeholders(placeholders)

    placeholders['USE_WALE'] = any(placeholders.get(n) for n in AUTO_ENABLE_WALG_RESTORE +
                                   ('WAL_SWIFT_BUCKET', 'WALE_SWIFT_PREFIX', 'WAL_GCS_BUCKET',
                                    'WAL_GS_BUCKET', 'WALE_GS_PREFIX', 'WALG_GS_PREFIX'))

    if placeholders.get('WALG_BACKUP_FROM_REPLICA'):
        placeholders['WALG_BACKUP_FROM_REPLICA'] = str(placeholders['WALG_BACKUP_FROM_REPLICA']).lower()

    # Kubernetes requires a callback to change the labels in order to point to the new master
    if USE_KUBERNETES:
        if placeholders.get('DCS_ENABLE_KUBERNETES_API'):
            if placeholders.get('KUBERNETES_USE_CONFIGMAPS'):
                placeholders['CALLBACK_SCRIPT'] = 'python3 /scripts/callback_endpoint.py'
        else:
            placeholders['CALLBACK_SCRIPT'] = 'python3 /scripts/callback_role.py'

    placeholders.setdefault('postgresql', {})
    placeholders['postgresql'].setdefault('parameters', {})
    placeholders['WALE_BINARY'] = 'wal-g' if placeholders.get('USE_WALG_BACKUP') == 'true' else 'wal-e'
    placeholders['postgresql']['parameters']['archive_command'] = \
        'envdir "{WALE_ENV_DIR}" {WALE_BINARY} wal-push "%p"'.format(**placeholders) \
        if placeholders['USE_WALE'] else '/bin/true'

    if os.path.exists(MEMORY_LIMIT_IN_BYTES_PATH):
        with open(MEMORY_LIMIT_IN_BYTES_PATH) as f:
            os_memory_mb = int(f.read()) / 1048576
    else:
        os_memory_mb = sys.maxsize
    os_memory_mb = min(os_memory_mb, os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES') / 1048576)

    # Depending on environment we take 1/4 or 1/5 of the memory, expressed in full MB's
    sb_ratio = 5 if USE_KUBERNETES else 4
    placeholders['postgresql']['parameters']['shared_buffers'] = '{}MB'.format(int(os_memory_mb/sb_ratio))
    # # 1 connection per 30 MB, at least 100, at most 1000
    placeholders['postgresql']['parameters']['max_connections'] = min(max(100, int(os_memory_mb/30)), 1000)

    placeholders['instance_data'] = get_instance_metadata(provider)

    placeholders['BGMON_LISTEN_IP'] = get_listen_ip()

    return placeholders


def write_file(config, filename, overwrite):
    if not overwrite and os.path.exists(filename):
        logging.warning('File %s already exists, not overwriting. (Use option --force if necessary)', filename)
    else:
        with open(filename, 'w') as f:
            logging.info('Writing to file %s', filename)
            f.write(config)


def pystache_render(*args, **kwargs):
    render = pystache.Renderer(missing_tags='strict')
    return render.render(*args, **kwargs)


def get_dcs_config(config, placeholders):
    if USE_KUBERNETES and placeholders.get('DCS_ENABLE_KUBERNETES_API'):
        try:
            kubernetes_labels = json.loads(placeholders.get('KUBERNETES_LABELS'))
        except (TypeError, ValueError) as e:
            logging.warning("could not parse kubernetes labels as a JSON: {0}, "
                            "reverting to the default: {1}".format(e, KUBERNETES_DEFAULT_LABELS))
            kubernetes_labels = json.loads(KUBERNETES_DEFAULT_LABELS)

        config = {'kubernetes': {'role_label': placeholders.get('KUBERNETES_ROLE_LABEL'),
                                 'scope_label': placeholders.get('KUBERNETES_SCOPE_LABEL'),
                                 'labels': kubernetes_labels}}
        if not placeholders.get('KUBERNETES_USE_CONFIGMAPS'):
            config['kubernetes'].update({'use_endpoints': True, 'pod_ip': placeholders['instance_data']['ip'],
                                         'ports': [{'port': 5432, 'name': 'postgresql'}]})
    elif 'ZOOKEEPER_HOSTS' in placeholders:
        config = {'zookeeper': {'hosts': yaml.load(placeholders['ZOOKEEPER_HOSTS'])}}
    elif 'EXHIBITOR_HOSTS' in placeholders and 'EXHIBITOR_PORT' in placeholders:
        config = {'exhibitor': {'hosts': yaml.load(placeholders['EXHIBITOR_HOSTS']),
                                'port': placeholders['EXHIBITOR_PORT']}}
    elif 'ETCD_HOST' in placeholders:
        config = {'etcd': {'host': placeholders['ETCD_HOST']}}
    elif 'ETCD_HOSTS' in placeholders:
        config = {'etcd': {'hosts': placeholders['ETCD_HOSTS']}}
    elif 'ETCD_DISCOVERY_DOMAIN' in placeholders:
        config = {'etcd': {'discovery_srv': placeholders['ETCD_DISCOVERY_DOMAIN']}}
    elif 'ETCD_URL' in placeholders:
        config = {'etcd': {'url': placeholders['ETCD_URL']}}
    elif 'ETCD_PROXY' in placeholders:
        config = {'etcd': {'proxy': placeholders['ETCD_PROXY']}}
    else:
        config = {}  # Configuration can also be specified using either SPILO_CONFIGURATION or PATRONI_CONFIGURATION

    if 'etcd' in config:
        config['etcd'].update({n.lower(): placeholders['ETCD_' + n]
                               for n in ('CACERT', 'KEY', 'CERT') if placeholders.get('ETCD_' + n)})

    if placeholders['NAMESPACE'] not in ('default', ''):
        config['namespace'] = placeholders['NAMESPACE']

    return config


def write_log_environment(placeholders):
    log_env = defaultdict(lambda: '')
    log_env.update(placeholders)

    aws_region = log_env.get('AWS_REGION')
    if not aws_region:
        aws_region = placeholders['instance_data']['zone'][:-1]
    log_env['LOG_AWS_HOST'] = 's3.{}.amazonaws.com'.format(aws_region)

    log_s3_key = 'spilo/{LOG_BUCKET_SCOPE_PREFIX}{SCOPE}{LOG_BUCKET_SCOPE_SUFFIX}/log/'.format(**log_env)
    log_s3_key += placeholders['instance_data']['id']
    log_env['LOG_S3_KEY'] = log_s3_key

    if not os.path.exists(log_env['LOG_TMPDIR']):
        os.makedirs(log_env['LOG_TMPDIR'])
        os.chmod(log_env['LOG_TMPDIR'], 0o1777)

    if not os.path.exists(log_env['LOG_ENV_DIR']):
        os.makedirs(log_env['LOG_ENV_DIR'])

    for var in ('LOG_TMPDIR', 'LOG_AWS_HOST', 'LOG_S3_KEY', 'LOG_S3_BUCKET', 'PGLOG'):
        write_file(log_env[var], os.path.join(log_env['LOG_ENV_DIR'], var), True)


def write_wale_environment(placeholders, prefix, overwrite):
    s3_names = ['WALE_S3_PREFIX', 'WALG_S3_PREFIX', 'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY',
                'WALE_S3_ENDPOINT', 'AWS_ENDPOINT', 'AWS_REGION', 'AWS_INSTANCE_PROFILE',
                'WALG_S3_SSE_KMS_ID', 'WALG_S3_SSE', 'WALG_DISABLE_S3_SSE', 'AWS_S3_FORCE_PATH_STYLE']
    gs_names = ['WALE_GS_PREFIX', 'WALG_GS_PREFIX', 'GOOGLE_APPLICATION_CREDENTIALS']
    swift_names = ['WALE_SWIFT_PREFIX', 'SWIFT_AUTHURL', 'SWIFT_TENANT', 'SWIFT_TENANT_ID', 'SWIFT_USER',
                   'SWIFT_USER_ID', 'SWIFT_USER_DOMAIN_NAME', 'SWIFT_USER_DOMAIN_ID', 'SWIFT_PASSWORD',
                   'SWIFT_AUTH_VERSION', 'SWIFT_ENDPOINT_TYPE', 'SWIFT_REGION', 'SWIFT_DOMAIN_NAME', 'SWIFT_DOMAIN_ID',
                   'SWIFT_PROJECT_NAME', 'SWIFT_PROJECT_ID', 'SWIFT_PROJECT_DOMAIN_NAME', 'SWIFT_PROJECT_DOMAIN_ID']

    walg_names = ['WALG_DELTA_MAX_STEPS', 'WALG_DELTA_ORIGIN', 'WALG_DOWNLOAD_CONCURRENCY',
                  'WALG_UPLOAD_CONCURRENCY', 'WALG_UPLOAD_DISK_CONCURRENCY', 'WALG_DISK_RATE_LIMIT',
                  'WALG_NETWORK_RATE_LIMIT', 'WALG_COMPRESSION_METHOD', 'USE_WALG_BACKUP',
                  'USE_WALG_RESTORE', 'WALG_BACKUP_COMPRESSION_METHOD', 'WALG_BACKUP_FROM_REPLICA',
                  'WALG_SENTINEL_USER_DATA', 'WALG_PREVENT_WAL_OVERWRITE']

    azure_names = ['WALE_WABS_PREFIX','WABS_ACCOUNT_NAME','WABS_ACCESS_KEY','WABS_SAS_TOKEN','WALG_AZ_PREFIX']

    wale = defaultdict(lambda: '')
    for name in ['WALE_ENV_DIR', 'SCOPE', 'WAL_BUCKET_SCOPE_PREFIX', 'WAL_BUCKET_SCOPE_SUFFIX',
                 'WAL_S3_BUCKET', 'WAL_GCS_BUCKET', 'WAL_GS_BUCKET', 'WAL_SWIFT_BUCKET'] +\
            s3_names + swift_names + gs_names + walg_names + azure_names:
        wale[name] = placeholders.get(prefix + name, '')

    if wale.get('WAL_S3_BUCKET') or wale.get('WALE_S3_PREFIX') or wale.get('WALG_S3_PREFIX'):
        wale_endpoint = wale.get('WALE_S3_ENDPOINT')
        aws_endpoint = wale.get('AWS_ENDPOINT')
        aws_region = wale.get('AWS_REGION')

        if not aws_region:
            # try to determine region from the endpoint or bucket name
            name = wale_endpoint or aws_endpoint or wale.get('WAL_S3_BUCKET') or wale.get('WALE_S3_PREFIX')
            match = re.search(r'.*(\w{2}-\w+-\d)-.*', name)
            if match:
                aws_region = match.group(1)
            else:
                aws_region = placeholders['instance_data']['zone'][:-1]

        if not aws_endpoint:
            if wale_endpoint:
                aws_endpoint = wale_endpoint.replace('+path://', '://')
                try:
                    idx = aws_endpoint.index('amazonaws.com:')
                    aws_endpoint = aws_endpoint[:idx + 13]
                except ValueError:
                    pass
            else:
                aws_endpoint = 'https://s3.{0}.amazonaws.com'.format(aws_region)

        if not wale_endpoint and aws_endpoint:
            wale_endpoint = aws_endpoint.replace('://', '+path://') + ':443'

        wale.update(WALE_S3_ENDPOINT=wale_endpoint, AWS_ENDPOINT=aws_endpoint, AWS_REGION=aws_region)
        if not (wale.get('AWS_SECRET_ACCESS_KEY') and wale.get('AWS_ACCESS_KEY_ID')):
            wale['AWS_INSTANCE_PROFILE'] = 'true'
        if wale.get('USE_WALG_BACKUP') and wale.get('WALG_DISABLE_S3_SSE') != 'true' and not wale.get('WALG_S3_SSE'):
            wale['WALG_S3_SSE'] = 'AES256'
        write_envdir_names = s3_names + walg_names
    elif wale.get('WAL_GCS_BUCKET') or wale.get('WAL_GS_BUCKET') or\
            wale.get('WALE_GCS_PREFIX') or wale.get('WALE_GS_PREFIX') or wale.get('WALG_GS_PREFIX'):
        if wale.get('WALE_GCS_PREFIX'):
            wale['WALE_GS_PREFIX'] = wale['WALE_GCS_PREFIX']
        elif wale.get('WAL_GCS_BUCKET'):
            wale['WAL_GS_BUCKET'] = wale['WAL_GCS_BUCKET']
        write_envdir_names = gs_names + walg_names
    elif wale.get('WAL_SWIFT_BUCKET') or wale.get('WALE_SWIFT_PREFIX'):
        write_envdir_names = swift_names
    else:
        return

    prefix_env_name = write_envdir_names[0]
    store_type = prefix_env_name[5:].split('_')[0]
    if not wale.get(prefix_env_name):  # WALE_*_PREFIX is not defined in the environment
        bucket_path = '/spilo/{WAL_BUCKET_SCOPE_PREFIX}{SCOPE}{WAL_BUCKET_SCOPE_SUFFIX}/wal/'.format(**wale)
        prefix_template = '{0}://{{WAL_{1}_BUCKET}}{2}'.format(store_type.lower(), store_type, bucket_path)
        wale[prefix_env_name] = prefix_template.format(**wale)
    # Set WALG_*_PREFIX for future compatibility
    if store_type in ('S3', 'GS') and not wale.get(write_envdir_names[1]):
        wale[write_envdir_names[1]] = wale[prefix_env_name]

    if not os.path.exists(wale['WALE_ENV_DIR']):
        os.makedirs(wale['WALE_ENV_DIR'])

    wale['WALE_LOG_DESTINATION'] = 'stderr'
    for name in write_envdir_names + ['WALE_LOG_DESTINATION']:
        if wale.get(name):
            write_file(wale[name], os.path.join(wale['WALE_ENV_DIR'], name), overwrite)

    if not os.path.exists(placeholders['WALE_TMPDIR']):
        os.makedirs(placeholders['WALE_TMPDIR'])
        os.chmod(placeholders['WALE_TMPDIR'], 0o1777)

    write_file(placeholders['WALE_TMPDIR'], os.path.join(wale['WALE_ENV_DIR'], 'TMPDIR'), True)


def update_and_write_wale_configuration(placeholders, prefix, overwrite):
    set_walg_placeholders(placeholders, prefix)
    write_wale_environment(placeholders, prefix, overwrite)


def write_clone_pgpass(placeholders, overwrite):
    pgpassfile = placeholders['CLONE_PGPASS']
    # pgpass is host:port:database:user:password
    r = {'host': escape_pgpass_value(placeholders['CLONE_HOST']),
         'port': placeholders['CLONE_PORT'],
         'database': '*',
         'user': escape_pgpass_value(placeholders['CLONE_USER']),
         'password': escape_pgpass_value(placeholders['CLONE_PASSWORD'])}
    pgpass_string = "{host}:{port}:{database}:{user}:{password}".format(**r)
    write_file(pgpass_string, pgpassfile, overwrite)
    uid = os.stat(placeholders['PGHOME']).st_uid
    os.chmod(pgpassfile, 0o600)
    os.chown(pgpassfile, uid, -1)


def check_crontab(user):
    with open(os.devnull, 'w') as devnull:
        cron_exit = subprocess.call(['crontab', '-lu', user], stdout=devnull, stderr=devnull)
        if cron_exit == 0:
            return logging.warning('Cron for %s is already configured. (Use option --force to overwrite cron)', user)
    return True


def setup_crontab(user, lines):
    lines += ['']  # EOF requires empty line for cron
    c = subprocess.Popen(['crontab', '-u', user, '-'], stdin=subprocess.PIPE)
    c.communicate(input='\n'.join(lines).encode())


def write_crontab(placeholders, overwrite):
    if not (overwrite or check_crontab('postgres')):
        return

    link_runit_service('cron')

    lines = ['PATH={PATH}'.format(**placeholders)]

    if placeholders.get('SSL_TEST_RELOAD'):
        env = ' '.join('{0}="{1}"'.format(n, placeholders[n]) for n in ('SSL_CA_FILE', 'SSL_CRL_FILE',
                       'SSL_CERTIFICATE_FILE', 'SSL_PRIVATE_KEY_FILE') if placeholders.get(n))
        lines += ['*/5 * * * * {0} /scripts/test_reload_ssl.sh 5'.format(env)]

    if bool(placeholders.get('USE_WALE')):
        lines += [('{BACKUP_SCHEDULE} envdir "{WALE_ENV_DIR}" /scripts/postgres_backup.sh' +
                   ' "{PGDATA}" {BACKUP_NUM_TO_RETAIN}').format(**placeholders)]

    if bool(placeholders.get('LOG_S3_BUCKET')):
        lines += [('{LOG_SHIP_SCHEDULE} nice -n 5 envdir "{LOG_ENV_DIR}"' +
                   ' /scripts/upload_pg_log_to_s3.py').format(**placeholders)]

    lines += yaml.load(placeholders['CRONTAB'])

    setup_crontab('postgres', lines)


def configure_renice(overwrite):
    if not (overwrite or check_crontab('root')):
        return

    try:
        os.nice(-1)
    except (OSError, PermissionError):
        return logging.info('Skipping creation of renice cron job due to lack of permissions')

    setup_crontab('root', ['*/5 * * * * bash /scripts/renice.sh'])
    os.nice(1)


def write_etcd_configuration(placeholders, overwrite=False):
    placeholders.setdefault('ETCD_HOST', '127.0.0.1:2379')
    link_runit_service('etcd')


def write_pam_oauth2_configuration(placeholders, overwrite):
    pam_oauth2_args = placeholders.get('PAM_OAUTH2') or ''
    t = pam_oauth2_args.split()
    if len(t) < 2:
        return logging.info("No PAM_OAUTH2 configuration was specified, skipping")

    r = urlparse(t[0])
    if not r.scheme or r.scheme != 'https':
        return logging.error('First argument of PAM_OAUTH2 must be a valid https url: %s', r)

    pam_oauth2_config = 'auth sufficient pam_oauth2.so {0}\n'.format(pam_oauth2_args)
    pam_oauth2_config += 'account sufficient pam_oauth2.so\n'

    write_file(pam_oauth2_config, '/etc/pam.d/postgresql', overwrite)


def write_pgbouncer_configuration(placeholders, overwrite):
    pgbouncer_config = placeholders.get('PGBOUNCER_CONFIGURATION')
    if not pgbouncer_config:
        return logging.info('No PGBOUNCER_CONFIGURATION was specified, skipping')

    pgbouncer_dir = '/run/pgbouncer'
    if not os.path.exists(pgbouncer_dir):
        os.makedirs(pgbouncer_dir)
    write_file(pgbouncer_config, pgbouncer_dir + '/pgbouncer.ini', overwrite)

    pgbouncer_auth = placeholders.get('PGBOUNCER_AUTHENTICATION') or placeholders.get('PGBOUNCER_AUTH')
    if pgbouncer_auth:
        write_file(pgbouncer_auth, pgbouncer_dir + '/userlist.txt', overwrite)

    link_runit_service('pgbouncer')


def get_binary_version(bin_dir):
    postgres = os.path.join(bin_dir or '', 'postgres')
    version = subprocess.check_output([postgres, '--version']).decode()
    version = re.match('^[^\s]+ [^\s]+ (\d+)\.(\d+)', version)
    return '.'.join(version.groups()) if int(version.group(1)) < 10 else version.group(1)


def main():
    debug = os.environ.get('DEBUG', '') in ['1', 'true', 'on', 'ON']
    args = parse_args()

    logging.basicConfig(format='%(asctime)s - bootstrapping - %(levelname)s - %(message)s', level=('DEBUG'
                        if debug else (args.get('loglevel') or 'INFO').upper()))

    provider = get_provider()
    placeholders = get_placeholders(provider)
    logging.info('Looks like your running %s', provider)

    if (provider == PROVIDER_LOCAL and
            not USE_KUBERNETES and
            'ETCD_HOST' not in placeholders and
            'ETCD_HOSTS' not in placeholders and
            'ETCD_URL' not in placeholders and
            'ETCD_PROXY' not in placeholders and
            'ETCD_DISCOVERY_DOMAIN' not in placeholders):
        write_etcd_configuration(placeholders)

    config = yaml.load(pystache_render(TEMPLATE, placeholders))
    config.update(get_dcs_config(config, placeholders))

    user_config = yaml.load(os.environ.get('SPILO_CONFIGURATION', os.environ.get('PATRONI_CONFIGURATION', ''))) or {}
    if not isinstance(user_config, dict):
        config_var_name = 'SPILO_CONFIGURATION' if 'SPILO_CONFIGURATION' in os.environ else 'PATRONI_CONFIGURATION'
        raise ValueError('{0} should contain a dict, yet it is a {1}'.format(config_var_name, type(user_config)))

    user_config_copy = deepcopy(user_config)
    config = deep_update(user_config_copy, config)

    # try to build bin_dir from PGVERSION environment variable if postgresql.bin_dir wasn't set in SPILO_CONFIGURATION
    if 'bin_dir' not in config['postgresql']:
        bin_dir = os.path.join('/usr/lib/postgresql', os.environ.get('PGVERSION', ''), 'bin')
        postgres = os.path.join(bin_dir, 'postgres')
        if os.path.isfile(postgres) and os.access(postgres, os.X_OK):  # check that there is postgres binary inside
            config['postgresql']['bin_dir'] = bin_dir

    version = float(get_binary_version(config['postgresql'].get('bin_dir')))
    if 'shared_preload_libraries' not in user_config.get('postgresql', {}).get('parameters', {}):
        libraries = [',' + n for n, v in extensions.items() if version >= v[0] and version <= v[1] and v[2]]
        config['postgresql']['parameters']['shared_preload_libraries'] += ''.join(libraries)
    if 'extwlist.extensions' not in user_config.get('postgresql', {}).get('parameters', {}):
        extwlist = [',' + n for n, v in extensions.items() if version >= v[0] and version <= v[1] and v[3]]
        config['postgresql']['parameters']['extwlist.extensions'] += ''.join(extwlist)

    # Ensure replication is available
    if 'pg_hba' in config['bootstrap'] and not any(['replication' in i for i in config['bootstrap']['pg_hba']]):
        rep_hba = 'hostssl replication {} all md5'.\
            format(config['postgresql']['authentication']['replication']['username'])
        config['bootstrap']['pg_hba'].insert(0, rep_hba)

    patroni_configfile = os.path.join(placeholders['PGHOME'], 'postgres.yml')

    for section in args['sections']:
        logging.info('Configuring {}'.format(section))
        if section == 'patroni':
            write_file(yaml.dump(config, default_flow_style=False, width=120), patroni_configfile, args['force'])
            link_runit_service('patroni')
            pg_socket_dir = '/run/postgresql'
            if not os.path.exists(pg_socket_dir):
                os.makedirs(pg_socket_dir)
                st = os.stat(placeholders['PGHOME'])
                os.chown(pg_socket_dir, st.st_uid, st.st_gid)
                os.chmod(pg_socket_dir, 0o2775)
        elif section == 'patronictl':
            configdir = os.path.join(placeholders['PGHOME'], '.config', 'patroni')
            patronictl_configfile = os.path.join(configdir, 'patronictl.yaml')
            if not os.path.exists(configdir):
                os.makedirs(configdir)
            if os.path.exists(patronictl_configfile):
                if not args['force']:
                    logging.warning('File %s already exists, not overriding. (Use option --force if necessary)',
                                    patronictl_configfile)
                    continue
                os.unlink(patronictl_configfile)
            os.symlink(patroni_configfile, patronictl_configfile)
        elif section == 'pgqd':
            link_runit_service('pgqd')
        elif section == 'log':
            if bool(placeholders.get('LOG_S3_BUCKET')):
                write_log_environment(placeholders)
        elif section == 'wal-e':
            if placeholders['USE_WALE']:
                write_wale_environment(placeholders, '', args['force'])
        elif section == 'certificate':
            write_certificates(placeholders, args['force'])
        elif section == 'crontab':
            if placeholders['CRONTAB'] or placeholders['USE_WALE'] or bool(placeholders.get('LOG_S3_BUCKET')):
                write_crontab(placeholders, args['force'])
        elif section == 'pam-oauth2':
            write_pam_oauth2_configuration(placeholders, args['force'])
        elif section == 'pgbouncer':
            write_pgbouncer_configuration(placeholders, args['force'])
        elif section == 'bootstrap':
            if placeholders['CLONE_WITH_WALE']:
                update_and_write_wale_configuration(placeholders, 'CLONE_', args['force'])
            if placeholders['CLONE_WITH_BASEBACKUP']:
                write_clone_pgpass(placeholders, args['force'])
        elif section == 'standby-cluster':
            if placeholders['STANDBY_WITH_WALE']:
                update_and_write_wale_configuration(placeholders, 'STANDBY_', args['force'])
        elif section == 'renice':
            configure_renice(args['force'])
        else:
            raise Exception('Unknown section: {}'.format(section))

    # We will abuse non zero exit code as an indicator for the launch.sh that it should not even try to create a backup
    sys.exit(int(not placeholders['USE_WALE']))


def escape_pgpass_value(val):
    output = []
    for c in val:
        if c in ('\\', ':'):
            output.append('\\')
        output.append(c)
    return ''.join(output)


if __name__ == '__main__':
    main()
