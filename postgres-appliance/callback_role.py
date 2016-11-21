#!/usr/bin/env python3

import json
import logging
import requests
import requests.exceptions
import os
import sys
import time

KUBE_SERVICE_DIR = '/var/run/secrets/kubernetes.io/serviceaccount/'
KUBE_NAMESPACE_FILENAME = KUBE_SERVICE_DIR + 'namespace'
KUBE_TOKEN_FILENAME = KUBE_SERVICE_DIR + 'token'
KUBE_CA_CERT = KUBE_SERVICE_DIR + 'ca.crt'

KUBE_API_URL = 'https://kubernetes.default.svc.cluster.local/api/v1/namespaces/{0}/pods/{1}'

logger = logging.getLogger(__name__)

NUM_ATTEMPTS = 10
LABEL = 'spilo-role'


def read_first_line(filename):
    try:
        with open(filename) as f:
            return f.readline().rstrip()
    except IOError:
        return None


def read_token():
    return read_first_line(KUBE_TOKEN_FILENAME)


def change_pod_role_label(new_role):
    pod_namespace = os.environ.get('POD_NAMESPACE', read_first_line(KUBE_NAMESPACE_FILENAME)) or 'default'
    api_url = KUBE_API_URL.format(pod_namespace, os.environ['HOSTNAME'])
    body = json.dumps({'metadata': {'labels': {LABEL: new_role}}})
    for i in range(NUM_ATTEMPTS):
        try:
            token = read_token()
            if token:
                r = requests.patch(api_url, data=body, verify=KUBE_CA_CERT,
                                   headers={'Content-Type': 'application/strategic-merge-patch+json',
                                            'Authorization': 'Bearer {0}'.format(token)})
                if r.status_code >= 300:
                    logger.warning('Unable to change the %s label to %s: %s', LABEL, new_role, r.text)
                else:
                    break
            else:
                logger.warning('Unable to read Kubernetes authorization token')
        except requests.exceptions.RequestException as e:
            logger.warning('Exception when executing PATCH on %s: %s', api_url, e)
        time.sleep(1)
    else:
        logger.error('Unable to set the label after %s attempts', NUM_ATTEMPTS)


def record_role_change(action, new_role):
    new_role = None if action == 'on_stop' else new_role
    logger.debug("Changing the pod's role to %s", new_role)
    change_pod_role_label(new_role)


def main():
    logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s', level=logging.INFO)
    if len(sys.argv) == 4 and sys.argv[1] in ('on_start', 'on_stop', 'on_role_change', 'on_restart'):
        record_role_change(action=sys.argv[1], new_role=sys.argv[2])
    else:
        sys.exit('Usage: %s <action> <role> <cluster_name>', sys.argv[0])
    return 0

if __name__ == '__main__':
    main()
