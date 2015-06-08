import boto
import requests
import subprocess
import time
import unittest

from boto.route53.record import Record
from etcd import EtcdManager, HouseKeeper

from test_etcd_manager import boto_ec2_connect_to_region, requests_get, requests_delete, MockResponse


def requests_put(url, **kwargs):
    response = MockResponse()
    response.status_code = 201
    return response


def raise_exception(*args, **kwargs):
    raise Exception()


class MockZone:

    def __init__(self, name):
        self.name = name

    def get_records(self):
        if self.name != 'test.':
            return []
        r = Record()
        r.name = '_etcd-server._tcp.cluster.' + self.name
        r.type = 'SRV'
        return [r]

    def add_record(self, type, name, value):
        pass

    def update_record(self, old, new_value):
        pass


class MockRoute53Connection:

    def get_zone(self, zone):
        return (None if zone == 'bla' else MockZone(zone))


def boto_route53_connect_to_region(region):
    return MockRoute53Connection()


class Popen:

    def __init__(self, args, **kwargs):
        if args[1] != 'cluster-health':
            raise Exception()
        self.stdout = ['cluster is healthy', 'member 15a694aa6a6003f4 is healthy',
                       'member effbc38ed2b11107 is unhealthy']

    def wait(self):
        pass


class TestHouseKeeper(unittest.TestCase):

    def __init__(self, method_name='runTest'):
        self.setUp = self.set_up
        super(TestHouseKeeper, self).__init__(method_name)

    def set_up(self):
        subprocess.Popen = Popen
        requests.get = requests_get
        requests.put = requests_put
        requests.delete = requests_delete
        boto.ec2.connect_to_region = boto_ec2_connect_to_region
        boto.route53.connect_to_region = boto_route53_connect_to_region
        self.manager = EtcdManager()
        self.manager.get_my_instace()
        self.manager.instance_id = 'i-deadbeef3'
        self.manager.region = 'eu-west-1'
        self.keeper = HouseKeeper(self.manager, 'test.')
        self.members_changed = self.keeper.members_changed()

    def test_members_changed(self):
        self.assertEqual(self.members_changed, True)
        self.keeper.members['blabla'] = True
        self.assertEqual(self.keeper.members_changed(), True)

    def test_is_leader(self):
        self.assertEqual(self.keeper.is_leader(), True)

    def test_acquire_lock(self):
        self.assertEqual(self.keeper.acquire_lock(), True)

    def test_remove_unhealthy_members(self):
        autoscaling_members = self.manager.get_autoscaling_members()
        self.assertEqual(self.keeper.remove_unhealthy_members(autoscaling_members), None)

    def test_update_route53_records(self):
        autoscaling_members = self.manager.get_autoscaling_members()
        self.assertEqual(self.keeper.update_route53_records(autoscaling_members), None)
        self.keeper.hosted_zone = 'bla'
        self.assertEqual(self.keeper.update_route53_records(autoscaling_members), None)
        self.keeper.hosted_zone = 'test2'
        self.assertEqual(self.keeper.update_route53_records(autoscaling_members), None)

    def test_cluster_unhealthy(self):
        self.assertEqual(self.keeper.cluster_unhealthy(), True)

    def test_run(self):
        time.sleep = raise_exception
        self.assertRaises(Exception, self.keeper.run)
        self.keeper.manager.etcd_pid = 1
        self.assertRaises(Exception, self.keeper.run)
        self.keeper.is_leader = raise_exception
        self.assertRaises(Exception, self.keeper.run)
