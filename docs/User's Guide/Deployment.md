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

	senza create DEFINITION.yaml VERSION HOSTED_ZONE DOCKER_IMAGE

This will create and execute a cloud formation template for you.

Example:

Argument   		   | Value
-------------------|-------
Definition         | etcd-appliance.yaml
Hosted zone 	   | acid.example.com
Version 		   | 1
Docker repository  | pierone.stups.zalan.do
Docker image       | acid/etcd-appliance
Image tag          | 0.2-SNAPSHOT

	senza create etcd-cluster.yaml 1 acid.example.com pierone.stups.zalan.do/acid/etcd-appliance:0.2-SNAPSHOT

Deploying Spilo using senza
===========================

* Have some global idea about the usage characteristics of the appliance
* Have unique name for the cluster

You can use senza init to create a senza definition for the spilo appliance,
the `ETCD_DISCOVERY_URL` should point to `HOSTED_ZONE` from the etcd-appliance that you want to use.

	senza init DEFINITION.yaml

Choose postgresapp as the template, senza will now prompt you for some information, you may want to override the defaults.

If you want, now is the time to edit `DEFINITION.yaml` to your needs.

To deploy the appliance using senza, do the following (we use `CLUSTER_NAME` for the `VERSION` that senza requires):

	senza create [OPTIONS] DEFINITION.yaml CLUSTER_NAME DOCKER_IMAGE

Example:

Argument   		   | Value
-------------------|-------
Definition		   | spilo.yaml
Cluster Name	   | pompeii
Docker repository  | pierone.stups.zalan.do
Docker image       | acid/spilo
Image tag          | 0.7-SNAPSHOT

	senza create spilo.yaml pompeii pierone.stups.zalan.do/acid/spilo:0.7-SNAPSHOT

You can now monitor the progress using:
	senza watch -n 2 DEFINITION.yaml CLUSTER_NAME

Connecting to the master
========================
You can now try to connect to the cluster (internally) using the generated dns-name, CLUSTER\_NAME.example.com.

When using the odd bastion host, you could create a tunnel to connect to the cluster as follows

	ssh -f -N -L 6543:CLUSTER_NAME.example.com:5432 odd.acid.zalan.do

You should be able to connect using psql locally:

	psql -h localhost -p 6543
