#!/usr/bin/env python

import json
import logging
import requests
import requests.exceptions
import os
import sys
import time

TOKEN_FILENAME = '/var/run/secrets/kubernetes.io/serviceaccount/token'
API_URL = 'https://{0}:{1}/api/v1/namespaces/default/pods/{2}'

logger = logging.getLogger(__name__)

NUM_ATTEMPTS = 5


def change_host_role_label(new_role):
    try:
        with open(TOKEN_FILENAME, "r") as f:
            token = f.read()
    except IOError:
        sys.exit("Unable to read K8S authorization token")

    headers = {'Authorization': 'Bearer {0}'.format(token)}
    headers['Content-Type'] = 'application/json-patch+json'
    url = API_URL.format(os.environ['KUBERNETES_SERVICE_HOST'],
                         os.environ['KUBERNETES_PORT_443_TCP_PORT'],
                         os.environ['HOSTNAME'])
    data = [{'op': 'add', 'path': '/metadata/labels/spilo-role', 'value': new_role}]
    for i in range(NUM_ATTEMPTS):
        try:
            r = requests.patch(url, headers=headers, data=json.dumps(data), verify=False)
            if r.status_code >= 300:
                logger.warning("Unable to change the role label to {0}: {1}".format(new_role, r.text))
            else:
                break
        except requests.exceptions.RequestException as e:
            logger.warning("Exception when executing POST on {0}: {1}".format(url, e))
        time.sleep(1)
    else:
        logger.warning("Unable to set the label after {0} attempts".format(NUM_ATTEMPTS))


def record_role_change(action, new_role):
    # on stop always sets the label to the replica, the load balancer
    # should not direct connections to the hosts with the stopped DB.
    if action == 'on_stop':
        new_role = 'replica'
    change_host_role_label(new_role)
    logger.debug("Changing the host's role to {0}".format(new_role))


def main():
    logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s', level=logging.INFO)
    if len(sys.argv) == 4 and sys.argv[1] in ('on_start', 'on_stop', 'on_role_change'):
        record_role_change(action=sys.argv[1], new_role=sys.argv[2])
    else:
        sys.exit("Usage: {0} action role name".format(sys.argv[0]))
    return 0

if __name__ == '__main__':
    main()
