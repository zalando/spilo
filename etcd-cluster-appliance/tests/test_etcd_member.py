#!/usr/bin/env python
# -*- coding: utf-8 -*-

import unittest
import requests

from etcd import EtcdMember
from boto.ec2.instance import Instance

from test_etcd_manager import requests_post, requests_delete, requests_get


class TestEtcdMember(unittest.TestCase):

    def __init__(self, method_name='runTest'):
        self.setUp = self.set_up
        super(TestEtcdMember, self).__init__(method_name)

    def set_up(self):
        self.old_requests_post = requests.post
        self.old_requests_get = requests.get
        self.old_requests_delete = requests.delete
        requests.post = requests_post
        requests.get = requests_get
        requests.delete = requests_delete
        self.ec2 = Instance()
        self.ec2.id = 'i-foobar'
        self.ec2.private_ip_address = '127.0.0.1'
        self.ec2.private_dns_name = 'ip-127-0-0-1.eu-west-1.compute.internal'
        self.ec2.tags = {'aws:cloudformation:stack-name': 'etc-cluster',
                         'aws:autoscaling:groupName': 'etc-cluster-postgres'}
        self.ec2_member = EtcdMember(self.ec2)
        self.etcd = {
            'id': 'deadbeef',
            'name': 'i-foobar2',
            'clientURLs': [],
            'peerURLs': ['http://127.0.0.2:{}'.format(EtcdMember.DEFAULT_PEER_PORT)],
        }
        self.etcd_member = EtcdMember(self.etcd)

    def test_get_addr_from_urls(self):
        self.assertEqual(self.ec2_member.get_addr_from_urls(['http://1.2:3']), '1.2')
        self.assertEqual(self.ec2_member.get_addr_from_urls(['http://1.2']), '1.2')
        self.assertEqual(self.ec2_member.get_addr_from_urls(['http//1.2']), None)

    def test_set_info_from_ec2_instance(self):
        self.assertEqual(self.etcd_member.addr, '127.0.0.2')
        self.etcd_member.set_info_from_ec2_instance(self.ec2)
        self.etcd_member.name = ''
        self.etcd_member.set_info_from_ec2_instance(self.ec2)

    def test_set_info_from_etcd(self):
        self.ec2_member.set_info_from_etcd(self.etcd)
        self.etcd['name'] = 'i-foobar'
        self.ec2_member.set_info_from_etcd(self.etcd)
        self.etcd['name'] = 'i-foobar2'

    def test_add_member(self):
        member = EtcdMember({
            'id': '',
            'name': '',
            'clientURLs': [],
            'peerURLs': ['http://127.0.0.2:{}'.format(EtcdMember.DEFAULT_PEER_PORT)],
        })
        self.assertEqual(self.ec2_member.add_member(member), True)
        member.addr = '127.0.0.4'
        self.assertEqual(self.ec2_member.add_member(member), False)

    def test_is_leader(self):
        self.assertEqual(self.ec2_member.is_leader(), True)

    def test_delete_member(self):
        member = EtcdMember({
            'id': 'ifoobari7',
            'name': 'i-sadfjhg',
            'clientURLs': ['http://127.0.0.2:{}'.format(EtcdMember.DEFAULT_CLIENT_PORT)],
            'peerURLs': ['http://127.0.0.2:{}'.format(EtcdMember.DEFAULT_PEER_PORT)],
        })
        self.assertEqual(self.ec2_member.delete_member(member), False)

    def test_get_leader(self):
        self.ec2_member.addr = '127.0.0.7'
        self.assertEqual(self.ec2_member.get_leader(), 'ifoobari1')

    def test_get_members(self):
        self.ec2_member.addr = '127.0.0.7'
        self.assertEqual(self.ec2_member.get_members(), [])


