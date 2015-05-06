Prerequisites
=============

AWS
---
You will need a VPC and be allowed to create new infrastructure.

Stups
-------------
To deploy spilo to AWS you will need the tooling from [stups](http://stups.readthedocs.org/en/latest).
The gist of it is to:

* have an AWS account with enough rights for deployment
* install Python 3.4
* install `stups-mai`
* install `stups-senza`

Before going any further ensure you can login to your VPC using the `stups` tooling.

Deploying etcd using senza
==========================

Deploying etcd should be a once in a VPC-lifetime thing. We can use `senza` to deploy the etcd appliance.

Prerequisites
--------
* `stups-senza`
* A [Senza Definition](http://stups.readthedocs.org/en/latest/components/senza.html#senza-definition), use the provided `etcd-appliance` as an example.
* The Security Group defined in the Senza Definition needs to be created

Create and execute
---------
To deploy the etcd-appliance, use the following:

	senza create [OPTIONS] DEFINITION VERSION HostedZone DockerImage

Example:

Argument   		| Value
----------------|-------
HostedZone 		| acid.example.com
Version 		| 1
DockerImage 	| etcd-appliance
DockerRevision 	| 0.1
Definition 		| etcd-appliance.yaml

	senza create etcd-cluster.yaml 1 acid.example.com etcd-appliance:0.1
