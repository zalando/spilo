#!/usr/bin/env python

from botocore.config import Config
import boto3
import logging
import os
import sys
import requests

logger = logging.getLogger(__name__)
LEADER_TAG_VALUE = os.environ.get('AWS_LEADER_TAG_VALUE', 'master')


def get_instance_metadata():
    response = requests.put(
        url='http://169.254.169.254/latest/api/token',  # AWS EC2 metadata service endpoint to get a token
        headers={'X-aws-ec2-metadata-token-ttl-seconds': '60'}
    )
    token = response.text
    instance_identity = requests.get(
        url='http://169.254.169.254/latest/dynamic/instance-identity/document',
        headers={'X-aws-ec2-metadata-token': token}
    )
    return instance_identity.json()


def associate_address(ec2, allocation_id, instance_id):
    return ec2.associate_address(InstanceId=instance_id, AllocationId=allocation_id, AllowReassociation=True)


def tag_resource(ec2, resource_id, tags):
    return ec2.create_tags(Resources=[resource_id], Tags=tags)


def list_volumes(ec2, instance_id):
    return ec2.describe_volumes(Filters=[{'Name': 'attachment.instance-id', 'Values': [instance_id]}])


def get_instance(ec2, instance_id):
    return ec2.describe_instances(InstanceIds=[instance_id])['Reservations'][0]['Instances'][0]


def main():
    logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s', level=logging.INFO)

    # EIP_ALLOCATION is optional argument
    argc = len(sys.argv)
    if argc not in (4, 5) or sys.argv[argc - 3] not in ('on_start', 'on_stop', 'on_role_change'):
        sys.exit("Usage: {0} [eip_allocation_id] action role name".format(sys.argv[0]))

    action, role, cluster = sys.argv[argc - 3:argc]

    metadata = get_instance_metadata()

    instance_id = metadata['instanceId']

    config = Config(
        region_name=metadata['region'],
        retries={
            'max_attempts': 10,
            'mode': 'standard'
        }
    )
    ec2 = boto3.client('ec2', config=config)

    if argc == 5 and role in ('primary', 'standby_leader') and action in ('on_start', 'on_role_change'):
        associate_address(ec2, sys.argv[1], instance_id)

    instance = get_instance(ec2, instance_id)

    tags = [{'Key': 'Role', 'Value': LEADER_TAG_VALUE if role == 'primary' else role}]
    tag_resource(ec2, instance_id, tags)

    tags.append({'Key': 'Instance', 'Value': instance_id})

    volumes = list_volumes(ec2, instance_id)
    for v in volumes['Volumes']:
        if any(tag['Key'] == 'Name' for tag in v.get('Tags', [])):
            tags_to_update = tags
        else:
            for attachment in v['Attachments']:
                volume_device = 'root' if attachment['Device'] == instance.get('RootDeviceName') else 'data'
                tags_to_update = tags + [{'Key': 'Name', 'Value': 'spilo_{}_{}'.format(cluster, volume_device)}]

        tag_resource(ec2, v.get('VolumeId'), tags_to_update)


if __name__ == '__main__':
    main()
