#!/usr/bin/env python

import boto3
import logging
import requests
import sys
import time

from botocore.exceptions import ClientError
from requests.exceptions import RequestException


logger = logging.getLogger(__name__)


def retry(func):
    def wrapped(*args, **kwargs):
        count = 0
        while True:
            try:
                return func(*args, **kwargs)
            except ClientError as e:
                if not (e.response['Error']['Code'] == 'Throttling' or 'RequestLimitExceeded' in str(e)):
                    raise
                logger.info('Throttling AWS API requests...')
            except RequestException:
                logger.exception('Exception when running %s', func)

            if count >= 10:
                break
            time.sleep(2 ** count * 0.5)
            count += 1
    return wrapped


@retry
def get_instance_metadata():
    response = requests.get('http://169.254.169.254/latest/dynamic/instance-identity/document')
    return response.json() if response.ok else {}


@retry
def associate_address(ec2, allocation_id, instance_id):
    return ec2.associate_address(AllocationId=allocation_id, InstanceId=instance_id, AllowReassociation=True)


@retry
def tag_instance(ec2, instance_id, tags):
    return ec2.create_tags(Resources=[instance_id], Tags=tags)


@retry
def list_volumes(ec2, instance_id):
    paginator = ec2.get_paginator('describe_volumes')
    for record_set in paginator.paginate(Filters=[{'Name': 'attachment.instance-id', 'Values': [instance_id]}]):
        for volume in record_set['Volumes']:
            yield volume['VolumeId']


@retry
def tag_volumes(ec2, instance_id, tags):
    return ec2.create_tags(Resources=list(list_volumes(ec2, instance_id)), Tags=tags)


def main():
    logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s', level=logging.INFO)
    if len(sys.argv) != 5 or sys.argv[2] not in ('on_start', 'on_stop', 'on_role_change'):
        sys.exit("Usage: {0} eip_allocation_id action role name".format(sys.argv[0]))

    action, role, cluster = sys.argv[2:5]

    metadata = get_instance_metadata()

    instance_id = metadata['instanceId']

    ec2 = boto3.client('ec2', region_name=metadata['region'])

    if role == 'master' and action in ('on_start', 'on_role_change'):
        associate_address(ec2, sys.argv[1], instance_id)

    tags = [{'Key': 'Role', 'Value': role}]
    tag_instance(ec2, instance_id, tags)

    tags += [{'Key': 'Instance', 'Value': instance_id}, {'Key': 'Name', 'Value': 'spilo_' + cluster}]
    tag_volumes(ec2, instance_id, tags)


if __name__ == '__main__':
    main()
