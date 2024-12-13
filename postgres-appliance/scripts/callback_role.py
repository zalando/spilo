#!/usr/bin/env python3

import json
import logging
import requests
import requests.exceptions
import os
import socket
import sys
import time

KUBE_SERVICE_DIR = '/var/run/secrets/kubernetes.io/serviceaccount/'
KUBE_NAMESPACE_FILENAME = KUBE_SERVICE_DIR + 'namespace'
KUBE_TOKEN_FILENAME = KUBE_SERVICE_DIR + 'token'
KUBE_CA_CERT = KUBE_SERVICE_DIR + 'ca.crt'

KUBE_API_URL = 'https://kubernetes.default.svc.cluster.local/api/v1/namespaces'

logger = logging.getLogger(__name__)

LABEL = os.environ.get("KUBERNETES_ROLE_LABEL", 'spilo-role')
LEADER_LABEL_VALUE = os.environ.get("KUBERNETES_LEADER_LABEL_VALUE", 'master')


def read_first_line(filename):
    try:
        with open(filename) as f:
            return f.readline().rstrip()
    except IOError:
        return None


def read_token():
    return read_first_line(KUBE_TOKEN_FILENAME)


def api_patch(namespace, kind, name, entity_name, body):
    api_url = '/'.join([KUBE_API_URL, namespace, kind, name])
    count = 0
    while True:
        try:
            token = read_token()
            if token:
                r = requests.patch(api_url, data=body, verify=KUBE_CA_CERT,
                                   headers={'Content-Type': 'application/strategic-merge-patch+json',
                                            'Authorization': 'Bearer {0}'.format(token)})
                if r.status_code in range(200, 206):
                    break
                logger.warning('Unable to change %s: %s', entity_name, r.text)
                if not (r.status_code in (500, 503, 504) or 'retry-after' in r.headers):
                    break
            else:
                logger.warning('Unable to read Kubernetes authorization token')
        except requests.exceptions.RequestException as e:
            logger.warning('Exception when executing PATCH on %s: %s', api_url, e)
        if count >= 10:
            raise Exception('PATCH {0} failed'.format(api_url))
        time.sleep(2 ** count * 0.5)
        count += 1


def change_pod_role_label(namespace, new_role):
    body = json.dumps({'metadata': {'labels': {LABEL: new_role}}})
    api_patch(namespace, 'pods', os.environ['HOSTNAME'], '{} label'.format(LABEL), body)


def change_endpoints(namespace, cluster):
    ip = socket.getaddrinfo(socket.gethostname(), 0, socket.AF_UNSPEC, socket.SOCK_STREAM, 0)[0][4][0]
    ip = os.environ.get('POD_IP', ip)
    body = json.dumps({'subsets': [{'addresses': [{'ip': ip}],
                                    'ports': [{'name': 'postgresql', 'port': 5432, 'protocol': 'TCP'}]}]})
    try:
        api_patch(namespace, 'endpoints', cluster, 'service endpoints', body)
    except Exception:
        pass


def record_role_change(action, new_role, cluster):
    new_role = None if action == 'on_stop' else new_role
    logger.debug("Changing the pod's role to %s", new_role)
    pod_namespace = os.environ.get('POD_NAMESPACE', read_first_line(KUBE_NAMESPACE_FILENAME)) or 'default'
    if new_role == LEADER_LABEL_VALUE:
        change_endpoints(pod_namespace, cluster)
    change_pod_role_label(pod_namespace, new_role)


def main():
    logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s', level=logging.INFO)
    if len(sys.argv) == 4 and sys.argv[1] in ('on_start', 'on_stop', 'on_role_change', 'on_restart'):
        record_role_change(action=sys.argv[1], new_role=sys.argv[2], cluster=sys.argv[3])
    else:
        sys.exit('Usage: %s <action> <role> <cluster_name>', sys.argv[0])
    return 0


if __name__ == '__main__':
    main()
