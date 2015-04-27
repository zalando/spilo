#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json
import unittest
import requests

from etcd import EtcdCluster, EtcdManager
from boto.ec2.instance import Instance


class MockResponse:

    def __init__(self):
        self.status_code = 200
        self.content = '{}'

    def json(self):
        return json.loads(self.content)


def requests_post(url, **kwargs):
    response = MockResponse()
    data = json.loads(kwargs['data'])
    if data['peerURLs'][0] in ['http://127.0.0.2:2380', 'http://127.0.0.3:2380']:
        response.status_code = 201
        response.content = '{{"id":"ifoobar","name":"","peerURLs":["{}"],"clientURLs":[""]}}'.format(data['peerURLs'
                ][0])
    else:
        response.status_code = 403
    return response


def requests_get(url, **kwargs):
    response = MockResponse()
    response.content = \
        '{"leaderInfo":{"leader":"ifoobari1"}, "members":[{"id":"ifoobari1","name":"i-deadbeef1","peerURLs":["http://127.0.0.1:2380"],"clientURLs":["http://127.0.0.1:2379"]},{"id":"ifoobari2","name":"i-deadbeef2","peerURLs":["http://127.0.0.2:2380"],"clientURLs":["http://127.0.0.2:2379"]},{"id":"ifoobari3","name":"i-deadbeef3","peerURLs":["http://127.0.0.3:2380"],"clientURLs":["ttp://127.0.0.3:2379"]},{"id":"ifoobari4","name":"i-deadbeef4","peerURLs":["http://127.0.0.4:2380"],"clientURLs":[]}]}'
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


class TestEtcdCluster(unittest.TestCase):

    def __init__(self, method_name='runTest'):
        self.setUp = self.set_up
        super(TestEtcdCluster, self).__init__(method_name)

    def set_up(self):
        requests.post = requests_post
        requests.get = requests_get
        requests.delete = requests_delete
        self.manager = EtcdManager()
        self.manager.get_autoscaling_members = manager_get_autoscaling_members
        self.manager.instance_id = 'i-deadbeef3'
        self.manager.region = 'eu-west-1'
        self.cluster = EtcdCluster(self.manager)
        self.cluster.load_members()

    def test_load_members(self):
        self.assertEqual(len(self.cluster.members), 4)
        self.assertNotEqual(self.cluster.me, None)

    def test_is_new_cluster(self):
        self.assertEqual(self.cluster.is_new_cluster(), False)

    def test_register_me(self):
        self.assertEqual(self.cluster.register_me(), [
            '-name',
            'i-deadbeef3',
            '--data-dir',
            'data',
            '-listen-peer-urls',
            'http://0.0.0.0:2380',
            '-initial-advertise-peer-urls',
            'http://127.0.0.3:2380',
            '-listen-client-urls',
            'http://0.0.0.0:2379',
            '-advertise-client-urls',
            'http://127.0.0.3:2379',
            '-initial-cluster',
            'i-deadbeef1=http://127.0.0.1:2380,i-deadbeef2=http://127.0.0.2:2380,i-deadbeef3=http://127.0.0.3:2380,i-deadbeef4=http://127.0.0.4:2380'
                ,
            '-initial-cluster-token',
            'etc-cluster',
            '-initial-cluster-state',
            'existing',
        ])

    def test_initialize_new_cluster(self):
        self.assertEqual(self.cluster.initialize_new_cluster(), [
            '-name',
            'i-deadbeef3',
            '--data-dir',
            'data',
            '-listen-peer-urls',
            'http://0.0.0.0:2380',
            '-initial-advertise-peer-urls',
            'http://127.0.0.3:2380',
            '-listen-client-urls',
            'http://0.0.0.0:2379',
            '-advertise-client-urls',
            'http://127.0.0.3:2379',
            '-initial-cluster',
            'i-deadbeef1=http://127.0.0.1:2380,i-deadbeef2=http://127.0.0.2:2380,i-deadbeef3=http://127.0.0.3:2380,i-deadbeef4=http://127.0.0.4:2380'
                ,
            '-initial-cluster-token',
            'etc-cluster',
            '-initial-cluster-state',
            'new',
        ])


