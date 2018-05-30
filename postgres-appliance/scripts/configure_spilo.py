#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import logging
import re
import os
import socket
import subprocess
import sys

from six.moves.urllib_parse import urlparse
from collections import defaultdict

import yaml
import pystache
import requests


PROVIDER_AWS = "aws"
PROVIDER_GOOGLE = "google"
PROVIDER_OPENSTACK = "openstack"
PROVIDER_LOCAL = "local"
PROVIDER_UNSUPPORTED = "unsupported"
USE_KUBERNETES = os.environ.get('KUBERNETES_SERVICE_HOST') is not None
KUBERNETES_DEFAULT_LABELS = '{"application": "spilo"}'
MEMORY_LIMIT_IN_BYTES_PATH = '/sys/fs/cgroup/memory/memory.limit_in_bytes'


def parse_args():
    sections = ['all', 'patroni', 'patronictl', 'certificate', 'wal-e', 'crontab',
                'pam-oauth2', 'pgbouncer', 'bootstrap', 'log']
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
bootstrap:
  post_init: /scripts/post_init.sh "{{HUMAN_ROLE}}"
  dcs:
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
        max_wal_senders: 5
        max_connections: {{postgresql.parameters.max_connections}}
        max_replication_slots: 5
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
    command: python3 /scripts/clone_with_s3.py --envdir "{{CLONE_WALE_ENV_DIR}}" --recovery-target-time="{{CLONE_TARGET_TIME}}"
    recovery_conf:
        restore_command: envdir "{{CLONE_WALE_ENV_DIR}}" /scripts/wale_restore_command.sh "%f" "%p"
        recovery_target_timeline: latest
        {{#USE_PAUSE_AT_RECOVERY_TARGET}}
        pause_at_recovery_target: false
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
  listen: 0.0.0.0:{{APIPORT}}
  connect_address: {{instance_data.ip}}:{{APIPORT}}
postgresql:
  use_unix_socket: true
  name: '{{instance_data.id}}'
  listen: 0.0.0.0:{{PGPORT}}
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
    ssl_cert_file: {{SSL_CERTIFICATE_FILE}}
    ssl_key_file: {{SSL_PRIVATE_KEY_FILE}}
    shared_preload_libraries: 'bg_mon,pg_stat_statements,pg_cron,set_user,pgextwlist'
    bg_mon.listen_address: '0.0.0.0'
    extwlist.extensions: 'btree_gin,btree_gist,citext,hstore,intarray,ltree,pgcrypto,pgq,pg_trgm,postgres_fdw,uuid-ossp,hypopg,pg_partman'
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
    - hostnossl all           all                all                reject
    {{#PAM_OAUTH2}}
    - hostssl all             +{{HUMAN_ROLE}}    all                pam
    {{/PAM_OAUTH2}}
    - hostssl all             all                all                md5

  {{#USE_WALE}}
  recovery_conf:
    restore_command: envdir "{{WALE_ENV_DIR}}" /scripts/wale_restore_command.sh "%f" "%p"
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
    command: patroni_wale_restore
    envdir: {{WALE_ENV_DIR}}
    threshold_megabytes: {{WALE_BACKUP_THRESHOLD_MEGABYTES}}
    threshold_backup_size_percentage: {{WALE_BACKUP_THRESHOLD_PERCENTAGE}}
    use_iam: 1
    retries: 2
    no_master: 1
  basebackup_fast_xlog:
    command: /scripts/basebackup.sh
    retries: 2
{{/USE_WALE}}
'''


def get_provider():
    try:
        logging.info("Figuring out my environment (Google? AWS? Openstack? Local?)")
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
    except (requests.exceptions.ConnectTimeout, requests.exceptions.ConnectionError):
        logging.info("Could not connect to 169.254.169.254, assuming local Docker setup")
        return PROVIDER_LOCAL


def get_instance_metadata(provider):
    metadata = {'ip': socket.gethostbyname(socket.gethostname()),
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
    elif provider == PROVIDER_AWS or provider == PROVIDER_OPENSTACK:
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


def set_clone_with_wale_placeholders(placeholders, provider):
    """ checks that enough parameters are provided to configure cloning with WAL-E """
    if 'CLONE_WAL_S3_BUCKET' in placeholders:
        clone_bucket_placeholder = 'CLONE_WAL_S3_BUCKET'
    elif 'CLONE_WAL_GSC_BUCKET' in placeholders:
        clone_bucket_placeholder = 'CLONE_WAL_GSC_BUCKET'
    else:
        logging.warning('Cloning with WAL-E is only possible when CLONE_WAL_S3_BUCKET or CLONE_WAL_GSC_BUCKET is set.')
        return
    # XXX: Cloning from one provider into another (i.e. Google from Amazon) is not possible.
    # No WAL-E related limitations, but credentials would have to be passsed explicitely.
    clone_cluster = placeholders.get('CLONE_SCOPE')
    if placeholders.get(clone_bucket_placeholder) and clone_cluster:
        placeholders['CLONE_WITH_WALE'] = True
        placeholders.setdefault('CLONE_WALE_ENV_DIR', os.path.join(placeholders['PGHOME'], 'etc', 'wal-e.d',
                                                                   'env-clone-{0}'.format(clone_cluster)))
    else:
        logging.warning("Clone method is set to WAL-E, but no '%s' or 'CLONE_SCOPE' specified",
                        clone_bucket_placeholder)


def get_placeholders(provider):
    placeholders = dict(os.environ)

    placeholders.setdefault('PGHOME', os.path.expanduser('~'))
    placeholders.setdefault('APIPORT', '8008')
    placeholders.setdefault('BACKUP_SCHEDULE', '00 01 * * *')
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
    placeholders.setdefault('PGPORT', '5432')
    placeholders.setdefault('SCOPE', 'dummy')
    placeholders.setdefault('SSL_CERTIFICATE_FILE', os.path.join(placeholders['PGHOME'], 'server.crt'))
    placeholders.setdefault('SSL_PRIVATE_KEY_FILE', os.path.join(placeholders['PGHOME'], 'server.key'))
    placeholders.setdefault('WALE_BACKUP_THRESHOLD_MEGABYTES', 1024)
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
    placeholders.setdefault('LOG_BUCKET_PREFIX', '{0}-'.format(placeholders['NAMESPACE'])
                            if placeholders['NAMESPACE'] not in ('default', '') else '')

    if placeholders['CLONE_METHOD'] == 'CLONE_WITH_WALE':
        # set_clone_with_wale_placeholders would modify placeholders and take care of error cases
        set_clone_with_wale_placeholders(placeholders, provider)
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

    if provider == PROVIDER_AWS:
        if not USE_KUBERNETES:  # AWS specific callback to tag the instances with roles
            if placeholders.get('EIP_ALLOCATION'):
                placeholders['CALLBACK_SCRIPT'] = 'python3 /scripts/callback_aws.py {0}'. \
                                                     format(placeholders['EIP_ALLOCATION'])
            else:
                placeholders['CALLBACK_SCRIPT'] = 'patroni_aws'

    placeholders['USE_WALE'] = bool(placeholders.get('WAL_S3_BUCKET') or placeholders.get('WAL_GCS_BUCKET'))

    # Kubernetes requires a callback to change the labels in order to point to the new master
    if USE_KUBERNETES:
        if placeholders.get('DCS_ENABLE_KUBERNETES_API'):
            if placeholders.get('KUBERNETES_USE_CONFIGMAPS'):
                placeholders['CALLBACK_SCRIPT'] = 'python3 /scripts/callback_endpoint.py'
        else:
            placeholders['CALLBACK_SCRIPT'] = 'python3 /scripts/callback_role.py'

    placeholders.setdefault('postgresql', {})
    placeholders['postgresql'].setdefault('parameters', {})
    placeholders['postgresql']['parameters']['archive_command'] = \
        'envdir "{0}" wal-e --aws-instance-profile wal-push "%p"'.format(placeholders['WALE_ENV_DIR']) \
        if placeholders['USE_WALE'] else '/bin/true'

    if os.path.exists(MEMORY_LIMIT_IN_BYTES_PATH):
        with open(MEMORY_LIMIT_IN_BYTES_PATH) as f:
            os_memory_mb = int(f.read()) / 1048576
    else:
        os_memory_mb = sys.maxsize
    os_memory_mb = min(os_memory_mb, os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES') / 1048576)

    # # We take 1/4 of the memory, expressed in full MB's
    placeholders['postgresql']['parameters']['shared_buffers'] = '{}MB'.format(int(os_memory_mb/4))
    # # 1 connection per 30 MB, at least 100, at most 1000
    placeholders['postgresql']['parameters']['max_connections'] = min(max(100, int(os_memory_mb/30)), 1000)

    placeholders['instance_data'] = get_instance_metadata(provider)
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
    elif 'ETCD_DISCOVERY_DOMAIN' in placeholders:
        config = {'etcd': {'discovery_srv': placeholders['ETCD_DISCOVERY_DOMAIN']}}
    else:
        config = {}  # Configuration can also be specified using either SPILO_CONFIGURATION or PATRONI_CONFIGURATION

    if placeholders['NAMESPACE'] not in ('default', ''):
        config['namespace'] = placeholders['NAMESPACE']

    return config


def write_log_environment(placeholders):

    log_env = defaultdict(lambda: '')
    log_env.update({
        name: placeholders.get(name, '')
        for name in [
            'SCOPE',
            'LOG_ENV_DIR',
            'LOG_S3_BUCKET',
            'LOG_BUCKET_SCOPE_PREFIX',
            'LOG_BUCKET_SCOPE_SUFFIX',
            'LOG_TMPDIR',
            'PGLOG',
            'AWS_REGION'
        ]
    })

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

    for var in [
        'LOG_TMPDIR',
        'LOG_AWS_HOST',
        'LOG_S3_KEY',
        'LOG_S3_BUCKET',
        'PGLOG',
    ]:
        write_file(log_env[var], os.path.join(log_env['LOG_ENV_DIR'], var), True)

    return


def write_wale_environment(placeholders, provider, prefix, overwrite):
    # Propagate missing variables as empty strings as that's generally easier
    # to work around than an exception in this code.
    envdir_names = ['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'WALE_S3_ENDPOINT', 'AWS_ENDPOINT',
                    'AWS_REGION', 'WALG_DELTA_MAX_STEPS', 'WALG_DELTA_ORIGIN',
                    'WALG_DOWNLOAD_CONCURRENCY', 'WALG_UPLOAD_CONCURRENCY', 'WALG_UPLOAD_DISK_CONCURRENCY']
    wale = defaultdict(lambda: '')
    wale.update({
        name: placeholders.get(prefix + name, '')
        for name in [
            'SCOPE',
            'WALE_ENV_DIR',
            'WAL_S3_BUCKET',
            'WAL_BUCKET_SCOPE_PREFIX',
            'WAL_BUCKET_SCOPE_SUFFIX',
            'WAL_GCS_BUCKET',
            'GOOGLE_APPLICATION_CREDENTIALS',
        ]
    })
    wale.update({name: placeholders[prefix + name] for name in envdir_names if prefix + name in placeholders})
    wale['BUCKET_PATH'] = '/spilo/{WAL_BUCKET_SCOPE_PREFIX}{SCOPE}{WAL_BUCKET_SCOPE_SUFFIX}/wal/'.format(**wale)
    wale['WALE_LOG_DESTINATION'] = 'stderr'

    if not os.path.exists(wale['WALE_ENV_DIR']):
        os.makedirs(wale['WALE_ENV_DIR'])

    if wale.get('WAL_S3_BUCKET'):
        wale_endpoint = wale.get('WALE_S3_ENDPOINT')
        aws_endpoint = wale.get('AWS_ENDPOINT')
        aws_region = wale.get('AWS_REGION')

        if not aws_region:
            match = re.search(r'.*(\w{2}-\w+-\d)-.*', wale_endpoint or aws_endpoint or wale['WAL_S3_BUCKET'])
            if match:
                aws_region = match.group(1)
            else:
                aws_region = placeholders['instance_data']['zone'][:-1]

        if not aws_endpoint:
            if wale_endpoint:
                aws_endpoint = wale_endpoint.replace('+path://', '://')
            else:
                aws_endpoint = 'https://s3.{0}.amazonaws.com:443'.format(aws_region)

        if not wale_endpoint and aws_endpoint:
            wale_endpoint = aws_endpoint.replace('://', '+path://')

        wale['WALE_S3_PREFIX'] = 's3://{WAL_S3_BUCKET}{BUCKET_PATH}'.format(**wale)
        wale.update(WALE_S3_ENDPOINT=wale_endpoint, AWS_ENDPOINT=aws_endpoint, AWS_REGION=aws_region)
        write_envdir_names = ['WALE_S3_PREFIX'] + envdir_names
    elif wale.get('WAL_GCS_BUCKET'):
        wale['WALE_GS_PREFIX'] = 'gs://{WAL_GCS_BUCKET}{BUCKET_PATH}'.format(**wale)
        write_envdir_names = ['WALE_GS_PREFIX', 'GOOGLE_APPLICATION_CREDENTIALS']
    else:
        return

    for name in write_envdir_names + ['WALE_LOG_DESTINATION']:
        if wale.get(name):
            write_file(wale[name], os.path.join(wale['WALE_ENV_DIR'], name), overwrite)

    if not os.path.exists(placeholders['WALE_TMPDIR']):
        os.makedirs(placeholders['WALE_TMPDIR'])
        os.chmod(placeholders['WALE_TMPDIR'], 0o1777)

    write_file(placeholders['WALE_TMPDIR'], os.path.join(wale['WALE_ENV_DIR'], 'TMPDIR'), True)


def write_bootstrap_configuration(placeholders, provider, overwrite):
    if placeholders['CLONE_WITH_WALE']:
        write_wale_environment(placeholders, provider, 'CLONE_', overwrite)
    if placeholders['CLONE_WITH_BASEBACKUP']:
        write_clone_pgpass(placeholders, overwrite)


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


def write_crontab(placeholders, overwrite):
    if not overwrite:
        with open(os.devnull, 'w') as devnull:
            cron_exit = subprocess.call(['crontab', '-lu', 'postgres'], stdout=devnull, stderr=devnull)
            if cron_exit == 0:
                return logging.warning('Cron is already configured. (Use option --force to overwrite cron)')

    lines = ['PATH={PATH}'.format(**placeholders)]
    lines += ['{BACKUP_SCHEDULE} /scripts/postgres_backup.sh "{WALE_ENV_DIR}" " {PGDATA}" "{BACKUP_NUM_TO_RETAIN}"'
            .format(**placeholders)]

    if bool(placeholders.get('LOG_S3_BUCKET')):
        lines += ['{LOG_SHIP_SCHEDULE} /backup_log.sh "{LOG_ENV_DIR}"'
            .format(**placeholders)]

    lines += yaml.load(placeholders['CRONTAB'])
    lines += ['']  # EOF requires empty line for cron

    c = subprocess.Popen(['crontab', '-u', 'postgres', '-'], stdin=subprocess.PIPE)
    c.communicate(input='\n'.join(lines).encode())


def write_etcd_configuration(placeholders, overwrite=False):
    placeholders.setdefault('ETCD_HOST', '127.0.0.1:2379')

    etcd_config = """\
[program:etcd]
user=postgres
autostart=1
priority=10
directory=/
command=env -i /bin/etcd --data-dir /tmp/etcd.data
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
redirect_stderr=true
"""
    write_file(etcd_config, '/etc/supervisor/conf.d/etcd.conf', overwrite)


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

    write_file(pgbouncer_config, '/etc/pgbouncer/pgbouncer.ini', overwrite)

    pgbouncer_auth = placeholders.get('PGBOUNCER_AUTHENTICATION') or placeholders.get('PGBOUNCER_AUTH')
    if pgbouncer_auth:
        write_file(pgbouncer_auth, '/etc/pgbouncer/userlist.txt', overwrite)

    supervisord_config = """\
[program:pgbouncer]
user=postgres
autostart=1
priority=500
directory=/
command=env -i /usr/sbin/pgbouncer /etc/pgbouncer/pgbouncer.ini
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
redirect_stderr=true
"""
    write_file(supervisord_config, '/etc/supervisor/conf.d/pgbouncer.conf', overwrite)


def main():
    debug = os.environ.get('DEBUG', '') in ['1', 'true', 'on', 'ON']
    args = parse_args()

    logging.basicConfig(format='%(asctime)s - bootstrapping - %(levelname)s - %(message)s', level=('DEBUG'
                        if debug else (args.get('loglevel') or 'INFO').upper()))

    if os.environ.get('PATRONIVERSION') < '1.0':
        raise Exception('Patroni version >= 1.0 is required')

    provider = os.environ.get('DEVELOP', '').lower() in ['1', 'true', 'on'] and PROVIDER_LOCAL or get_provider()
    placeholders = get_placeholders(provider)
    logging.info('Looks like your running %s', provider)

    if (provider == PROVIDER_LOCAL and
            not USE_KUBERNETES and
            'ETCD_HOST' not in placeholders and
            'ETCD_DISCOVERY_DOMAIN' not in placeholders):
        write_etcd_configuration(placeholders)

    config = yaml.load(pystache_render(TEMPLATE, placeholders))
    config.update(get_dcs_config(config, placeholders))

    user_config = yaml.load(os.environ.get('SPILO_CONFIGURATION', os.environ.get('PATRONI_CONFIGURATION', ''))) or {}
    if not isinstance(user_config, dict):
        config_var_name = 'SPILO_CONFIGURATION' if 'SPILO_CONFIGURATION' in os.environ else 'PATRONI_CONFIGURATION'
        raise ValueError('{0} should contain a dict, yet it is a {1}'.format(config_var_name, type(user_config)))

    config = deep_update(user_config, config)

    # try to build bin_dir from PGVERSION environment variable if postgresql.bin_dir wasn't set in SPILO_CONFIGURATION
    if 'bin_dir' not in config['postgresql']:
        bin_dir = os.path.join('/usr/lib/postgresql', os.environ.get('PGVERSION', ''), 'bin')
        postgres = os.path.join(bin_dir, 'postgres')
        if os.path.isfile(postgres) and os.access(postgres, os.X_OK):  # check that there is postgres binary inside
            config['postgresql']['bin_dir'] = bin_dir

    # Ensure replication is available
    if 'pg_hba' in config['bootstrap'] and not any(['replication' in i for i in config['bootstrap']['pg_hba']]):
        rep_hba = 'hostssl replication {} 0.0.0.0/0 md5'.\
            format(config['postgresql']['authentication']['replication']['username'])
        config['bootstrap']['pg_hba'].insert(0, rep_hba)

    patroni_configfile = os.path.join(placeholders['PGHOME'], 'postgres.yml')

    for section in args['sections']:
        logging.info('Configuring {}'.format(section))
        if section == 'patroni':
            write_file(yaml.dump(config, default_flow_style=False, width=120), patroni_configfile, args['force'])
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
        elif section == 'log':
            if bool(placeholders.get('LOG_S3_BUCKET')):
                write_log_environment(placeholders)
        elif section == 'wal-e':
            if placeholders['USE_WALE']:
                write_wale_environment(placeholders, provider, '', args['force'])
        elif section == 'certificate':
            write_certificates(placeholders, args['force'])
        elif section == 'crontab':
            # create crontab only if there are tasks for it
            if placeholders['USE_WALE'] or bool(placeholders.get('LOG_S3_BUCKET')):
                write_crontab(placeholders, args['force'])
        elif section == 'pam-oauth2':
            write_pam_oauth2_configuration(placeholders, args['force'])
        elif section == 'pgbouncer':
            write_pgbouncer_configuration(placeholders, args['force'])
        elif section == 'bootstrap':
            write_bootstrap_configuration(placeholders, provider, args['force'])
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
