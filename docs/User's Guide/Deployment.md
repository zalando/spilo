Prerequisites
=============

You will need a VPC and be allowed to create new infrastructure.

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
If you already have other spilo-instances running, you may reuse the already running etcd-appliance.

The following prerequisites need to be met.

* `stups-senza`
* A [Senza Definition](http://stups.readthedocs.org/en/latest/components/senza.html#senza-definition), use the provided `etcd-appliance.yaml` as an example.
* The Security Group defined in the Senza Definition needs to be created

To deploy the etcd-appliance, use the following:

	senza create [OPTIONS] DEFINITION VERSION HOSTED_ZONE DOCKER_IMAGE:IMAGE_TAG

This will create and execute a cloud formation template for you.

Example:

Argument   		| Value
----------------|-------
Hosted zone 	| acid.example.com
Version 		| 1
Docker image 	| etcd-appliance
Image tag	 	| 0.1
Definition 		| etcd-appliance.yaml

	senza create etcd-cluster.yaml 1 acid.example.com etcd-appliance:0.1

Deploying Spilo using senza
===========================

* Have some global idea about the usage characteristics of the appliance
* Have unique name for the cluster

To deploy the appliance using senza, do the following:

	senza create [OPTIONS] CLUSTER_NAME ETCD_DISCOVERY_URL DOCKER_IMAGE:IMAGE_TAG

The `ETCD_DISCOVERY_URL` should point to `HOSTED_ZONE` from the etcd-appliance that you want to use.

Example:

Argument   		   | Value
-------------------|-------
Cluster Name	   | pompeii
etcd discovery url | acid.example.com
Docker image       | spilo
Image tag          | 0.6-SNAPSHOT

	senza create spilo.yaml pompeii etcd.acid.example.com spilo:0.6-SNAPSHOT
