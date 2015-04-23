Introduction
============
This etcd appliance is created for an AWS environment. It is available as an etcd cluster internally, for any application willing to use it. For discovery of the appliance we consider having a recently updated DNS SRV record.

Design
======
The appliance supposed to be run on EC2 instances, members of one autoscaling group.
Usage of autoscaling group give us possibility to discover all cluster member via AWS api (python-boto).
Etcd process is executed by python wrapper which is taking care about discovering all members of already existing cluster or the new cluster.
Currently the following scenarios are supported:
- Starting up of the new cluster. etcd.py will figure out that this is the new cluster and run etcd daemon with necessary options.
- If the new EC2 instance is spawned within existing autoscaling group etcd.py will take care about adding this instance into already existing cluster and apply needed options to etcd daemon.
- If something happened with etcd (crached or exited), etcd.py will remove data directory and then remove and add this instance from/into existing cluster. (Not sure that this is the good strategy)

TODO
====
- [ ] Periodically one of the cluster members must check cluster health and remove unhealthy members from it.
- [ ] Periodically one of the cluster members should update SRV record in a predifined zone via AWS api.
