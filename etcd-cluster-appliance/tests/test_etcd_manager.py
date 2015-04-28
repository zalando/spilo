#!/usr/bin/env python
# -*- coding: utf-8 -*-

import boto.ec2
import json
import unittest
import requests

from etcd import EtcdManager
from boto.ec2.instance import Instance


class MockResponse:

    def __init__(self):
        self.status_code = 200
        self.content = '{}'

    def json(self):
        return json.loads(self.content)


class MockReservation:

    def __init__(self, instance):
        self.instances = [instance]


class MockEc2Connection:

    def generate_instance(self, id, ip):
        i = Instance()
        i.id = id
        i.private_ip_address = ip
        i.private_dns_name = 'ip-{}.eu-west-1.compute.internal'.format(ip.replace('.', '-'))
        i.tags = {'aws:cloudformation:stack-name': 'etc-cluster', 'aws:autoscaling:groupName': 'etc-cluster-postgres'}
        return i

    def get_all_reservations(self, filters=None):
        return [MockReservation(self.generate_instance('i-deadbeef1', '127.0.0.1')),
                MockReservation(self.generate_instance('i-deadbeef2', '127.0.0.2')),
                MockReservation(self.generate_instance('i-deadbeef3', '127.0.0.3'))]


def requests_get(url, **kwargs):
    response = MockResponse()
    if 'instance-identity' in url:
        response.content = '{"region":"eu-west-1", "instanceId": "i-deadbeef3"}'
    return response


def boto_ec2_connect_to_region(region):
    return MockEc2Connection()


class TestEtcdManager(unittest.TestCase):

    def __init__(self, method_name='runTest'):
        self.setUp = self.set_up
        super(TestEtcdManager, self).__init__(method_name)

    def set_up(self):
        requests.get = requests_get
        boto.ec2.connect_to_region = boto_ec2_connect_to_region
        self.manager = EtcdManager()
        self.manager.find_my_instace()

    def test_get_autoscaling_members(self):
        self.assertEqual(len(self.manager.get_autoscaling_members()), 3)
        self.assertEqual(self.manager.instance_id, 'i-deadbeef3')
        self.assertEqual(self.manager.region, 'eu-west-1')


