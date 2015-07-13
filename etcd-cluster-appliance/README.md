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
- Periodically leader performs cluster health check and remove cluster members which are not members of autoscaling group
- Also it creates or updates SRV record in a given zone via AWS api.

Usage
=====

    senza create etcd-cluster.yaml STACK_VERSION HOSTED_ZONE DOCKER_IMAGE MINT_BUCKET SCALYR_KEY
    senza create etcd-cluster.yaml 1 myteam.example.org pierone.example.org/myteam/etcd:0.1-SNAPSHOT zalando-stups-mint-123456789123-eu-west-1 abc123def
