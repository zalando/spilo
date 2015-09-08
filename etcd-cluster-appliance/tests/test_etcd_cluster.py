import boto.ec2
import requests
import unittest

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
