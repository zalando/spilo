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

## Step 1: Define an application
Before starting with clusters, you will need to define an application under whose name your clusters will be created.
This is done in `Kio`_ or its graphical interface `Yourturn`_. Assuming for the example that the application is being
created under the team `elephant`, we might choose this app ID: `elephant-etcd`.

## Step 2: Create an etcd cluster
A cluster can be creating by issuing such a command:

    senza create etcd-cluster.yaml STACK_VERSION APP_ID HOSTED_ZONE DOCKER_IMAGE MINT_BUCKET SCALYR_KEY

For example, if you made are making an etcd cluster to be used by a service called `foo`, you could issue the following:

    senza create etcd-cluster.yaml for-foo \
                                   elephant-etcd \
                                   elephant.example.org \
                                   pierone.example.org/elephant/etcd:0.1-SNAPSHOT \
                                   zalando-stups-mint-123456789123-eu-west-1 abc123def

The idea is to have a single application ID, here it is `elephant-etcd`, and then create different versions, i.e. 
different clusters by varying the `STACK_VERSION` parameter depending on the purpose you want to use that specific 
cluster for.

## Step 3: Confirm successful cluster creation
Running this `senza create` command should have created:
- the required amount of EC2 instances
    - with stack name `elephant-etcd`
    - with instance name `elephant-etcd-for-foo`
- a security group allowing etcd's ports 2379 and 2380
- a role that allows reading `elephant-etcd` app's Mint bucket
- DNS records
    - an A record of the form `for-foo.elephant.example.org.`
    - a SRV record of the form `_etcd-server._tcp.for-foo.elephant.example.org.`


.. _Kio: https://github.com/zalando-stups/kio
.. _Yourturn: https://github.com/zalando-stups/yourturn

