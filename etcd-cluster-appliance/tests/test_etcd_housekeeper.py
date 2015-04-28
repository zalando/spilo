#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json
import unittest
import requests

from etcd import EtcdManager, HouseKeeper
from boto.ec2.instance import Instance


class MockResponse:

    def __init__(self):
        self.status_code = 200
        self.content = '{}'

    def json(self):
        return json.loads(self.content)


def requests_get(url, **kwargs):
    response = MockResponse()
    response.content = \
        '{"leaderInfo":{"leader":"ifoobari1"}, "members":[{"id":"ifoobari1","name":"i-deadbeef1","peerURLs":["http://127.0.0.1:2380"],"clientURLs":["http://127.0.0.1:2379"]},{"id":"ifoobari2","name":"i-deadbeef2","peerURLs":["http://127.0.0.2:2380"],"clientURLs":["http://127.0.0.2:2379"]},{"id":"ifoobari3","name":"i-deadbeef3","peerURLs":["http://127.0.0.3:2380"],"clientURLs":["ttp://127.0.0.3:2379"]},{"id":"ifoobari4","name":"i-deadbeef4","peerURLs":["http://127.0.0.4:2380"],"clientURLs":[]}]}'
    return response


def requests_put(url, **kwargs):
    response = MockResponse()
    response.status_code = 201
    return response


def requests_delete(url, **kwargs):
    response = MockResponse()
    response.status_code = 204
    return response


def generate_instance(id, ip):
    i = Instance()
    i.id = id
    i.private_ip_address = ip
    i.private_dns_name = 'ip-{}.eu-west-1.compute.internal'.format(ip.replace('.', '-'))
    i.tags = {'aws:cloudformation:stack-name': 'etc-cluster', 'aws:autoscaling:groupName': 'etc-cluster-postgres'}
    return i


def manager_get_autoscaling_members():
    return [generate_instance('i-deadbeef1', '127.0.0.1'), generate_instance('i-deadbeef2', '127.0.0.2'),
            generate_instance('i-deadbeef3', '127.0.0.3')]


class TestHouseKeeper(unittest.TestCase):

    def __init__(self, method_name='runTest'):
        self.setUp = self.set_up
        super(TestHouseKeeper, self).__init__(method_name)

    def set_up(self):
        requests.get = requests_get
        requests.put = requests_put
        requests.delete = requests_delete
        self.manager = EtcdManager()
        self.manager.instance_id = 'i-deadbeef3'
        self.manager.region = 'eu-west-1'
        self.keeper = HouseKeeper(self.manager, 'test.')
        self.members_changed = self.keeper.members_changed()

    def test_members_changed(self):
        self.assertEqual(self.members_changed, True)

    def test_is_leader(self):
        self.assertEqual(self.keeper.is_leader(), True)

    def test_acquire_lock(self):
        self.assertEqual(self.keeper.acquire_lock(), True)

    def test_remove_unhealthy_members(self):
        autoscaling_members = manager_get_autoscaling_members()
        self.assertEqual(self.keeper.remove_unhealthy_members(autoscaling_members), None)


