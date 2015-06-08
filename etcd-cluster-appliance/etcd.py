#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function

import boto.ec2
import boto.route53
import json
import logging
import os
import requests
import shutil
import signal
import subprocess
import sys
import time

from boto.ec2.instance import Instance
from threading import Thread

if sys.hexversion >= 0x03000000:
    from urllib.parse import urlparse
else:
    from urlparse import urlparse


class EtcdMember:

    API_TIMEOUT = 3
    API_VERSION = '/v2/'
    DEFAULT_CLIENT_PORT = 2379
    DEFAULT_PEER_PORT = 2380
    AG_TAG = 'aws:autoscaling:groupName'

    def __init__(self, arg):
        self.is_accessible = False
        self.id = None  # id of cluster member, could be obtained only from running cluster
        self.name = None  # name of cluster member, always mactch with the AWS instance.id
        self.instance_id = None
        self.addr = None  # private ip address of the instance
        self.cluster_token = None
        self.autoscaling_group = None

        self.client_port = self.DEFAULT_CLIENT_PORT
        self.peer_port = self.DEFAULT_PEER_PORT

        self.client_urls = []  # these values could be assigned only from the running etcd
        self.peer_urls = []  # cluster by performing http://addr:client_port/v2/members api call

        if isinstance(arg, Instance):
            self.set_info_from_ec2_instance(arg)
        else:
            self.set_info_from_etcd(arg)

    def set_info_from_ec2_instance(self, instance):
        # by convention member.name == instance.id
        if self.name and self.name != instance.id:
            return

        # when you add new member it doesn't have name, but we can match it by peer_addr
        if self.addr and self.addr != instance.private_ip_address:
            return

        self.instance_id = instance.id
        self.addr = instance.private_ip_address
        self.dns = instance.private_dns_name
        self.cluster_token = instance.tags['aws:cloudformation:stack-name']
        self.autoscaling_group = instance.tags[self.AG_TAG]

    @staticmethod
    def get_addr_from_urls(urls):
        for url in urls:
            url = urlparse(url)
            if url and url.netloc:
                arr = url.netloc.split(':', 1)
                # TODO: check that arr[0] contains ip
                return arr[0]
        return None

    def set_info_from_etcd(self, info):
        # by convention member.name == instance.id
        if self.instance_id and info['name'] and self.instance_id != info['name']:
            return

        addr = self.get_addr_from_urls(info['peerURLs'])
        # when you add new member it doesn't have name, but we can match it by peer_addr
        if self.addr and (not addr or self.addr != addr):
            return

        self.id = info['id']
        self.name = info['name']
        self.client_urls = info['clientURLs']
        self.peer_urls = info['peerURLs']
        self.addr = addr

    @staticmethod
    def generate_url(addr, port):
        return 'http://{}:{}'.format(addr, port)

    def get_client_url(self, endpoint=''):
        url = self.generate_url(self.addr, self.client_port)
        if endpoint:
            url += self.API_VERSION + endpoint
        return url

    def get_peer_url(self):
        return self.generate_url(self.addr, self.peer_port)

    def api_get(self, endpoint):
        url = self.get_client_url(endpoint)
        response = requests.get(url, timeout=self.API_TIMEOUT)
        logging.debug('Got response from GET %s: code=%s content=%s', url, response.status_code, response.content)
        return (response.json() if response.status_code == 200 else None)

    def api_put(self, endpoint, data):
        url = self.get_client_url(endpoint)
        response = requests.put(url, data=data)
        logging.debug('Got response from PUT %s %s: code=%s content=%s', url, data, response.status_code,
                      response.content)
        return (response.json() if response.status_code == 201 else None)

    def api_post(self, endpoint, data):
        url = self.get_client_url(endpoint)
        headers = {'Content-type': 'application/json'}
        data = json.dumps(data)
        response = requests.post(url, data=data, headers=headers)
        logging.debug('Got response from POST %s %s: code=%s content=%s', url, data, response.status_code,
                      response.content)
        return (response.json() if response.status_code == 201 else None)

    def api_delete(self, endpoint):
        url = self.get_client_url(endpoint)
        response = requests.delete(url)
        logging.debug('Got response from DELETE %s: code=%s content=%s', url, response.status_code, response.content)
        return response.status_code == 204

    def is_leader(self):
        return not self.api_get('stats/leader') is None

    def get_leader(self):
        json = self.api_get('stats/self')
        return (json['leaderInfo']['leader'] if json else None)

    def get_members(self):
        json = self.api_get('members')
        return (json['members'] if json else [])

    def add_member(self, member):
        logging.debug('Adding new member %s:%s to cluster', member.instance_id, member.get_peer_url())
        response = self.api_post('members', {'peerURLs': [member.get_peer_url()]})
        if response:
            member.set_info_from_etcd(response)
            return True
        return False

    def delete_member(self, member):
        logging.debug('Removing member %s from cluster', member.id)
        return self.api_delete('members/' + member.id)

    def etcd_arguments(self, data_dir, initial_cluster, cluster_state):
        return [
            '-name',
            self.instance_id,
            '--data-dir',
            data_dir,
            '-listen-peer-urls',
            'http://0.0.0.0:{}'.format(self.peer_port),
            '-initial-advertise-peer-urls',
            self.get_peer_url(),
            '-listen-client-urls',
            'http://0.0.0.0:{}'.format(self.client_port),
            '-advertise-client-urls',
            self.get_client_url(),
            '-initial-cluster',
            initial_cluster,
            '-initial-cluster-token',
            self.cluster_token,
            '-initial-cluster-state',
            cluster_state,
        ]


class EtcdCluster:

    def __init__(self, manager):
        self.manager = manager
        self.me = None
        self.accessible_member = None

    @staticmethod
    def merge_member_lists(ec2_members, etcd_members):
        members = dict((m.get_peer_url(), m) for m in ec2_members)
        for m in etcd_members:
            existing_members = [members[u] for u in m['peerURLs'] if u in members]
            if existing_members:
                members[existing_members[0].get_peer_url()].set_info_from_etcd(m)
            else:
                m = EtcdMember(m)
                members[m.get_peer_url()] = m
        return sorted(members.values(), key=lambda e: e.instance_id or e.name)

    def load_members(self):
        self.accessible_member = None
        self.leader = None
        leader = None
        ec2_members = map(EtcdMember, self.manager.get_autoscaling_members())
        etcd_members = []
        for member in ec2_members:
            if member.instance_id != self.manager.instance_id:
                try:
                    leader = member.get_leader()
                    etcd_members = member.get_members()
                    if etcd_members:
                        self.accessible_member = member
                        break
                except:
                    logging.exception('Load members from etcd')

        self.members = self.merge_member_lists(ec2_members, etcd_members)

        for m in self.members:
            if leader and m.id == leader:
                self.leader = m
            if self.manager.instance_id in [m.instance_id, m.name]:
                self.me = m

    def is_new_cluster(self):
        return self.accessible_member is None or self.me.id and self.me.name and len(self.me.client_urls) == 0

    def initialize_new_cluster(self):
        peers = ','.join(['{}={}'.format(m.instance_id or m.name, m.get_peer_url()) for m in self.members
                         if m.instance_id or m.peer_urls])
        logging.debug('Initializing new cluster with members %s', peers)
        return self.me.etcd_arguments(self.manager.DATA_DIR, peers, 'new')

    def register_me(self):
        if self.is_new_cluster():
            return self.initialize_new_cluster()

        logging.debug('Trying to register myself in existing cluster')

        if not self.leader or not self.accessible_member:
            raise Exception('Etcd cluster does not have leader yet. Can not add myself')

        add_member = False
        if len(self.me.client_urls) > 0:
            if not self.accessible_member.delete_member(self.me):
                raise Exception('Can not remove my old instance from etcd cluster')
            add_member = True
        elif not self.me.id:
            add_member = True

        if add_member and not self.accessible_member.add_member(self.me):
            raise Exception('Can not register myself in etcd cluster')

        peers = ','.join(['{}={}'.format(m.instance_id or m.name, m.get_peer_url()) for m in self.members
                         if m.peer_urls])
        return self.me.etcd_arguments(self.manager.DATA_DIR, peers, 'existing')


class EtcdManager:

    ETCD_BINARY = '/bin/etcd'
    DATA_DIR = 'data'
    NAPTIME = 5

    def __init__(self):
        self.region = None
        self.instance_id = None
        self.me = None
        self.etcd_pid = 0

    def load_my_identities(self):
        url = 'http://169.254.169.254/latest/dynamic/instance-identity/document'
        response = requests.get(url)
        if response.status_code != 200:
            raise Exception('Got error from %s: code=%s content=%s', url, response.status_code, response.content)
        json = response.json()
        self.region = json['region']
        self.instance_id = json['instanceId']

    def find_my_instace(self):
        if not self.instance_id or not self.region:
            self.load_my_identities()

        conn = boto.ec2.connect_to_region(self.region)
        for r in conn.get_all_reservations(filters={'instance_id': self.instance_id}):
            for i in r.instances:
                if i.id == self.instance_id:
                    return (EtcdMember(i) if EtcdMember.AG_TAG in i.tags else None)
        return None

    def get_my_instace(self):
        if not self.me:
            self.me = self.find_my_instace()
        return self.me

    def get_autoscaling_members(self):
        me = self.get_my_instace()

        conn = boto.ec2.connect_to_region(self.region)
        res = conn.get_all_reservations(filters={'tag:{}'.format(EtcdMember.AG_TAG): me.autoscaling_group})

        return [i for r in res for i in r.instances if i.state != 'terminated' and i.tags.get(EtcdMember.AG_TAG, '')
                == me.autoscaling_group]

    def clean_data_dir(self):
        path = self.DATA_DIR
        try:
            if os.path.islink(path):
                os.unlink(path)
            elif not os.path.exists(path):
                return
            elif os.path.isfile(path):
                os.remove(path)
            elif os.path.isdir(path):
                shutil.rmtree(path)
        except:
            logging.exception('Can not remove %s', path)

    def run(self):
        cluster = EtcdCluster(self)
        while True:
            try:
                cluster.load_members()

                args = cluster.register_me()

                self.etcd_pid = os.fork()
                if self.etcd_pid == 0:
                    self.clean_data_dir()
                    os.execv(self.ETCD_BINARY, [self.ETCD_BINARY] + args)

                logging.warning('Started new etcd process with pid: %s and args: %s', self.etcd_pid, args)
                pid, status = os.waitpid(self.etcd_pid, 0)
                logging.warning('Porcess %s finished with exit code %s', pid, status >> 8)
                self.etcd_pid = 0
            except KeyboardInterrupt:
                logging.warning('Got keyboard interrupt, exiting...')
                break
            except Exception:
                logging.exception('Exception in main loop')
            logging.warning('Sleeping %s seconds before next try...', self.NAPTIME)
            time.sleep(self.NAPTIME)


class HouseKeeper(Thread):

    NAPTIME = 30

    def __init__(self, manager, hosted_zone):
        super(HouseKeeper, self).__init__()
        self.daemon = True
        self.manager = manager
        self.me = EtcdMember({
            'id': None,
            'name': None,
            'peerURLs': ['http://127.0.0.1:{}'.format(EtcdMember.DEFAULT_PEER_PORT)],
            'clientURLs': [],
        })
        self.hosted_zone = hosted_zone
        self.members = {}
        self.unhealthy_members = {}

    def is_leader(self):
        return self.me.is_leader()

    def acquire_lock(self):
        data = data = {'value': self.manager.instance_id, 'ttl': self.NAPTIME, 'prevExist': False}
        return not self.me.api_put('keys/_self_maintenance_lock', data=data) is None

    def members_changed(self):
        old_members = self.members.copy()
        new_members = self.me.get_members()
        changed = False
        for m in new_members:
            if not m['id'] in old_members or old_members.pop(m['id']) != m:
                changed = True
        if old_members:
            changed = True
        if changed:
            self.members = dict((m['id'], m) for m in new_members)
        return changed

    def cluster_unhealthy(self):
        process = subprocess.Popen([self.manager.ETCD_BINARY + 'ctl', 'cluster-health'], stdout=subprocess.PIPE)
        ret = any([True for line in process.stdout if 'is unhealthy' in line])
        process.wait()
        return ret

    def remove_unhealthy_members(self, autoscaling_members):
        members = {}
        for m in self.members.values():
            m = EtcdMember(m)
            members[m.addr] = m

        for m in autoscaling_members:
            members.pop(m.private_ip_address, None)

        for m in members.values():
            self.me.delete_member(m)

    def update_srv_record(self, autoscaling_members):
        stack_version = self.manager.me.cluster_token.split('-')[-1]
        record_name = '.'.join(['_etcd-server._tcp', stack_version, self.hosted_zone])
        record_type = 'SRV'

        conn = boto.route53.connect_to_region('universal')
        zone = conn.get_zone(self.hosted_zone)
        if not zone:
            return

        old_record = None
        for r in zone.get_records():
            if r.type.upper() == record_type and r.name.lower().startswith(record_name):
                old_record = r
                break

        members = {}
        for m in self.members.values():
            m = EtcdMember(m)
            members[m.addr] = m

        new_value = [' '.join(map(str, [1, 1, members[i.private_ip_address].peer_port, i.private_dns_name])) for i in
                     autoscaling_members if i.private_ip_address in members]

        if old_record:
            if set(old_record.resource_records) != set(new_value):
                zone.update_record(old_record, new_value)
        else:
            zone.add_record(record_type, record_name, new_value)

    def run(self):
        update_required = False
        while True:
            try:
                if self.manager.etcd_pid != 0 and self.is_leader():
                    if (update_required or self.members_changed() or self.cluster_unhealthy()) and self.acquire_lock():
                        update_required = True
                        autoscaling_members = self.manager.get_autoscaling_members()
                        if autoscaling_members:
                            self.remove_unhealthy_members(autoscaling_members)
                            self.update_srv_record(autoscaling_members)
                            update_required = False
                else:
                    self.members = {}
                    update_required = False
            except:
                logging.exception('Exception in HouseKeeper main loop')
            logging.debug('Sleeping %s seconds...', self.NAPTIME)
            time.sleep(self.NAPTIME)


def sigterm_handler(signo, stack_frame):
    sys.exit()


def main():
    hosted_zone = os.environ.get('HOSTED_ZONE', None)
    manager = EtcdManager()
    try:
        house_keeper = HouseKeeper(manager, hosted_zone)
        house_keeper.start()
        manager.run()
    finally:
        logging.info('Trying to remove myself from cluster...')
        try:
            cluster = EtcdCluster(manager)
            cluster.load_members()
            if cluster.accessible_member:
                if cluster.me:
                    if not cluster.accessible_member.delete_member(cluster.me):
                        logging.error('Can not remove myself from cluster')
                else:
                    logging.error('Can not find me in existing cluster')
            else:
                logging.error('Cluster does not have accessible member')
        except:
            logging.exception('Failed to remove myself from cluster')


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, sigterm_handler)
    logging.basicConfig(format='%(levelname)-6s %(asctime)s - %(message)s', level=logging.DEBUG)
    main()
