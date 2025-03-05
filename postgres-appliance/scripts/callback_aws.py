#!/usr/bin/env python

import boto.ec2
import boto.utils
import logging
import os
import sys
import time

logger = logging.getLogger(__name__)
LEADER_TAG_VALUE = os.environ.get('AWS_LEADER_TAG_VALUE', 'master')


def retry(func):
    def wrapped(*args, **kwargs):
        count = 0
        while True:
            try:
                return func(*args, **kwargs)
            except boto.exception.BotoServerError as e:
                if count >= 10 or str(e.error_code) not in ('Throttling', 'RequestLimitExceeded'):
                    raise
                logger.info('Throttling AWS API requests...')
                time.sleep(2 ** count * 0.5)
                count += 1

    return wrapped


def get_instance_metadata():
    return boto.utils.get_instance_identity()['document']


@retry
def associate_address(ec2, allocation_id, instance_id):
    return ec2.associate_address(instance_id=instance_id, allocation_id=allocation_id, allow_reassociation=True)


@retry
def tag_resource(ec2, resource_id, tags):
    return ec2.create_tags([resource_id], tags)


@retry
def list_volumes(ec2, instance_id):
    return ec2.get_all_volumes(filters={'attachment.instance-id': instance_id})


@retry
def get_instance(ec2, instance_id):
    return ec2.get_only_instances([instance_id])[0]


def main():
    logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s', level=logging.INFO)

    # EIP_ALLOCATION is optional argument
    argc = len(sys.argv)
    if argc not in (4, 5) or sys.argv[argc - 3] not in ('on_start', 'on_stop', 'on_role_change'):
        sys.exit("Usage: {0} [eip_allocation_id] action role name".format(sys.argv[0]))

    action, role, cluster = sys.argv[argc - 3:argc]

    metadata = get_instance_metadata()

    instance_id = metadata['instanceId']

    ec2 = boto.ec2.connect_to_region(metadata['region'])

    if argc == 5 and role in ('primary', 'standby_leader') and action in ('on_start', 'on_role_change'):
        associate_address(ec2, sys.argv[1], instance_id)

    instance = get_instance(ec2, instance_id)

    tags = {'Role': LEADER_TAG_VALUE if role == 'primary' else role}
    tag_resource(ec2, instance_id, tags)

    tags.update({'Instance': instance_id})

    volumes = list_volumes(ec2, instance_id)
    for v in volumes:
        if 'Name' in v.tags:
            tags_to_update = tags
        else:
            if v.attach_data.device == instance.root_device_name:
                volume_device = 'root'
            else:
                volume_device = 'data'
            tags_to_update = dict(tags, Name='spilo_{}_{}'.format(cluster, volume_device))

        tag_resource(ec2, v.id, tags_to_update)


if __name__ == '__main__':
    main()
