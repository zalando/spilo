import boto.ec2
import json
import os
import requests
import time
import unittest

from boto.ec2.instance import Instance
from etcd import EtcdManager


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
    if url == 'http://127.0.0.1:2379/v2/stats/self':
        raise Exception()
    response = MockResponse()
    if url == 'http://127.0.0.7:2379/v2/members':
        response.content = '{"members":[]}'
    else:
        response.content = \
            '{"region":"eu-west-1", "instanceId": "i-deadbeef3", "leaderInfo":{"leader":"ifoobari1"}, "members":[{"id":"ifoobari1","name":"i-deadbeef1","peerURLs":["http://127.0.0.1:2380"],"clientURLs":["http://127.0.0.1:2379"]},{"id":"ifoobari2","name":"i-deadbeef2","peerURLs":["http://127.0.0.2:2380"],"clientURLs":["http://127.0.0.2:2379"]},{"id":"ifoobari3","name":"i-deadbeef3","peerURLs":["http://127.0.0.3:2380"],"clientURLs":["ttp://127.0.0.3:2379"]},{"id":"ifoobari4","name":"i-deadbeef4","peerURLs":["http://127.0.0.4:2380"],"clientURLs":[]}]}'
    return response


def requests_get_bad_status(url, **kwargs):
    response = requests_get(url, **kwargs)
    response.status_code = 404
    return response


def requests_delete(url, **kwargs):
    response = MockResponse()
    response.status_code = (500 if url.endswith('/v2/members/ifoobari7') else 204)
    return response


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


def boto_ec2_connect_to_region(region):
    return MockEc2Connection()


def raise_exception(_):
    raise Exception()


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

    def test_clean_data_dir(self):
        self.manager.clean_data_dir()
        os.mkdir(self.manager.DATA_DIR)
        self.manager.clean_data_dir()
        open(self.manager.DATA_DIR, 'w').close()
        self.manager.clean_data_dir()
        os.symlink('foo', self.manager.DATA_DIR)
        old_unlink = os.unlink
        os.unlink = raise_exception
        self.manager.clean_data_dir()
        os.unlink = old_unlink
        self.manager.clean_data_dir()

    def test_load_my_identities(self):
        requests.get = requests_get_bad_status
        self.assertRaises(Exception, self.manager.load_my_identities)

    def test_run(self):
        os.execv = raise_exception
        os.fork = lambda: 0
        time.sleep = raise_exception
        self.assertRaises(Exception, self.manager.run)
        os.fork = lambda: 1
        os.waitpid = lambda a, b: (1, 0)
        self.assertRaises(Exception, self.manager.run)
