#!/usr/bin/env python
# -*- coding: utf-8 -*-

import boto.ec2
import unittest
import requests

from etcd import EtcdCluster, EtcdManager

from test_etcd_manager import requests_post, requests_delete, requests_get, boto_ec2_connect_to_region


class TestEtcdCluster(unittest.TestCase):

    def __init__(self, method_name='runTest'):
        self.setUp = self.set_up
        super(TestEtcdCluster, self).__init__(method_name)

    def set_up(self):
        requests.post = requests_post
        requests.get = requests_get
        requests.delete = requests_delete
        boto.ec2.connect_to_region = boto_ec2_connect_to_region
        self.manager = EtcdManager()
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
        self.cluster.me.id = 'ifoobari7'
        self.assertRaises(Exception, self.cluster.register_me)
        self.cluster.me.client_urls = []
        self.cluster.me.id = ''
        self.cluster.me.addr = '127.0.0.4'
        self.assertRaises(Exception, self.cluster.register_me)
        self.cluster.leader = None
        self.assertRaises(Exception, self.cluster.register_me)
        self.cluster.accessible_member = None
        self.assertEqual(self.cluster.register_me()[17], 'new')


