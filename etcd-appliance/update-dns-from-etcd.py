#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
The purpose of this tool is to keep certain DNS records up to date with a etcd cluster membership list.
"""

import time
import logging
import urllib2
import os

def update_dns_records(dns_members, etcd_members):
    print "Updating dns records"
    urllib2.urlopen('http://localhost:2031')
    pass

def fetch_dns_members():
    return ['a','b','c']

def etcd_put(path, data):
    opener = urllib2.build_opener(urllib2.HTTPHandler)
    request = urllib2.Request(path, data)
    request.get_method = lambda: 'PUT'
    opener.open(request)

def acquire_lock(naptime, prevExists=False):
    etcd_put("http://localhost:4001/v2/keys/acquire_dns_update_lock", {"ttl": naptime, "prevExists": prevExists}) 

def fetch_etcd_members():
    return ['d','e','f']

def main():
    naptime = 30

    ## use LOGLEVEL and DEBUG environment variables to control logging
    loglevel = os.environ.get('LOGLEVEL','WARNING').upper()
    if (os.environ.get('DEBUG','0').lower() in ('','1','yes','y','true','t')):
        loglevel = 'DEBUG'
    logging.basicConfig(level=loglevel)

    while(True):
        try:
            if acquire_lock(naptime):
                logging.debug("Fetching members from dns")
                dns_members  = fetch_dns_members()
                logging.debug("Fetching members from etcd")
                etcd_members = fetch_etcd_members()

                if set(dns_members) != set(etcd_members):
                    api_members = fetch_api_members()
                    if set(api_members) != set(etcd_members):
                        update_dns_records(dns_members=dns_members, etcd_members=etcd_members)
            else:
                ## Some other member is already doing what I'm doing
                pass

        ## We are a daemon, and should keep running
        except Exception:
            logging.exception("Uncaught exception")
        finally:
            logging.debug("Napping for {} seconds".format(naptime))
            time.sleep(naptime)

if __name__ == '__main__':
    main()
