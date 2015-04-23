#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function

import boto.ec2
import json
import logging
import os
import requests
import shutil
import time


class EtcdCluster:

    ETCD_BINARY = './etcd'
    DATA_DIR = 'data'
    API_TIMEOUT = 3
    CLIENT_PORT = 2379
    PEER_PORT = 2380
    AG_TAG = 'aws:autoscaling:groupName'
    NAPTIME = 5

    def __init__(self):
        self.region = None
        self.my_id = None
        self.me = None
        self.etcd_pid = 0

    def load_my_identities(self):
        url = 'http://169.254.169.254/latest/dynamic/instance-identity/document'
        response = requests.get(url)
        if response.status_code != 200:
            raise Exception('Got error from %s: code=%s content=%s', url, response.status_code, response.content)
        json = response.json()
        self.region = json['region']
        self.my_id = json['instanceId']

    def find_my_instace(self):
        if not self.my_id or not self.region:
            self.load_my_identities()

        conn = boto.ec2.connect_to_region(self.region)
        for r in conn.get_all_reservations():
            for i in r.instances:
                if i.id == self.my_id:
                    return (i if self.AG_TAG in i.tags else None)
        return None

    def get_my_instace(self):
        if not self.me:
            self.me = self.find_my_instace()
        return self.me

    def get_autoscaling_members(self):
        me = self.get_my_instace()

        grp = me.tags[self.AG_TAG]
        conn = boto.ec2.connect_to_region(self.region)
        res = conn.get_all_reservations(filters={'tag:{}'.format(self.AG_TAG): grp})

        return [i for r in res for i in r.instances if i.state != 'terminated' and i.tags.get(self.AG_TAG, '') == grp]

    def call_cluster_api(self, instance, params):
        url = 'http://{}:{}/v2/{}'.format(instance.private_ip_address, self.CLIENT_PORT, params)
        response = requests.get(url, timeout=self.API_TIMEOUT)
        if response.status_code == 200:
            return response.json()
        raise Exception('Request failed: {}'.format(url))

    def get_cluster_members(self, instance):
        json = self.call_cluster_api(instance, 'members')
        logging.debug('Got response from %s: %s', instance.id, json)
        if not 'members' in json:
            raise Exception('Got invalid response from instance %s' % instance.id)
        return json['members']

    def get_cluster_leader(self, instance):
        json = self.call_cluster_api(instance, 'stats/self')
        logging.debug('Got response from %s: %s', instance.id, json)
        return json['leaderInfo']['leader']

    def get_cluster_info(self, instances):
        for instance in instances:
            if instance.id != self.me.id:
                try:
                    leader = self.get_cluster_leader(instance)
                    members = self.get_cluster_members(instance)
                    return {'leader': leader, 'members': members, 'accessible_member': instance.id}
                except:
                    pass
        return None

    def is_new_cluster(self, info):
        for member in info['members']:
            if member['name'] == self.me.id:
                return len(member.get('clientURLs', [])) == 0
        return False

    def etcd_arguments(self, initial_cluster, cluster_state):
        return [
            '-name',
            self.me.id,
            '--data-dir',
            self.DATA_DIR,
            '-listen-peer-urls',
            'http://0.0.0.0:{}'.format(self.PEER_PORT),
            '-initial-advertise-peer-urls',
            'http://{}:{}'.format(self.me.private_ip_address, self.PEER_PORT),
            '-listen-client-urls',
            'http://0.0.0.0:{}'.format(self.CLIENT_PORT),
            '-advertise-client-urls',
            'http://{}:{}'.format(self.me.private_ip_address, self.CLIENT_PORT),
            '-initial-cluster',
            initial_cluster,
            '-initial-cluster-token',
            self.me.tags['aws:cloudformation:stack-name'],
            '-initial-cluster-state',
            cluster_state,
        ]

    def initialize_new_cluster(self, instances):
        peers = ','.join(['{}=http://{}:{}'.format(i.id, i.private_ip_address, self.PEER_PORT) for i in instances])
        logging.debug('Initializing new cluster with members %s', peers)
        return self.etcd_arguments(peers, 'new')

    def delete_member(self, accessible_member, id):
        logging.debug('Removing member %s from cluster', id)
        response = requests.delete(accessible_member['clientURLs'][0] + '/v2/members/' + id, timeout=self.API_TIMEOUT)
        logging.debug('Got response from %s: code=%s content=%s', accessible_member['clientURLs'][0],
                      response.status_code, response.content)
        return response.status_code == 204

    def add_member(self, accessible_member, peer_url):
        logging.debug('Adding new member %s to cluster', peer_url)
        url = accessible_member['clientURLs'][0] + '/v2/members'
        data = json.dumps({'peerURLs': [peer_url]})
        headers = {'Content-type': 'application/json'}
        response = requests.post(url, data=data, headers=headers, timeout=self.API_TIMEOUT)
        logging.debug('Got response from %s: code=%s content=%s', accessible_member['clientURLs'][0],
                      response.status_code, response.content)
        ret = (response.json() if response.status_code == 201 else None)
        if ret:
            ret['name'] = self.me.id
        return ret

    def add_me_to_cluster(self, info):
        logging.debug('Trying to register myself in existing cluster')
        if not info['leader']:
            logging.warning('Etcd cluster does not have leader yet. Can not add myself')
            return False

        my_peer_url = 'http://{}:{}'.format(self.me.private_ip_address, self.PEER_PORT)
        accessible_member = None
        me = None
        for member in info['members']:
            if member['name'] == info['accessible_member']:
                accessible_member = member
            elif not me and (member['name'] == self.me.id or my_peer_url in member['peerURLs']):
                me = member

        cluster_state = 'existing'
        members = [m for m in info['members'] if m != me]

        if me:
            if len(me.get('clientURLs', [])) > 0:
                if not self.delete_member(accessible_member, me['id']):
                    logging.warning('Can not remove my old instance from etcd cluster')
                    return False
                me = None
            elif me['name']:
                cluster_state = 'new'

        if not me:
            me = self.add_member(accessible_member, my_peer_url)
            if not me:
                logging.warning('Can not register myself in etcd cluster')
                return False

        peers = ','.join(['{}={}'.format(m['name'], m['peerURLs'][0]) for m in members + [me]])
        return self.etcd_arguments(peers, cluster_state)

    def clean_data_dir(self):
        path = self.DATA_DIR
        if not os.path.exists(path):
            return
        try:
            if os.path.islink(path):
                os.unlink(path)
            elif os.path.isfile(path):
                os.remove(path)
            elif os.path.isdir(path):
                shutil.rmtree(path)
        except:
            logging.exception('Can not remove %s', path)

    def run(self):
        while True:
            try:
                instances = self.get_autoscaling_members()
                info = self.get_cluster_info(instances)
                if not info or self.is_new_cluster(info):
                    args = self.initialize_new_cluster(instances)
                else:
                    args = self.add_me_to_cluster(info)

                self.etcd_pid = os.fork()
                if self.etcd_pid == 0:
                    self.clean_data_dir()
                    os.execv(self.ETCD_BINARY, [self.ETCD_BINARY] + args)

                logging.warning('Started new etcd process with pid: %s and args: %s', self.etcd_pid, args)
                pid, status = os.waitpid(self.etcd_pid, 0)
                logging.warning('Porcess %d finished with exit code %d', pid, status >> 8)
                self.etcd_pid = 0
            except KeyboardInterrupt:
                logging.warning('Got keyboard interrupt, exiting...')
                break
            except Exception:
                logging.exception('Exception in main loop')
            logging.warning('Sleeping %d seconds before next try...', self.NAPTIME)
            time.sleep(self.NAPTIME)


def main():
    etcd = EtcdCluster()
    etcd.run()


if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.realpath(__file__)))
    main()
