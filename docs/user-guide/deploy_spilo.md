Prerequisites
=============

* Have an etcd-cluster available
* Have some global idea about the usage characteristics of the appliance
* Have unique name for the cluster

You can use senza init to create a senza definition for the spilo appliance,
the `ETCD_DISCOVERY_DOMAIN` should point to `HOSTED_ZONE` from the etcd-appliance that you want to use.

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
Docker repository  | registry.opensource.zalan.do
Docker image       | spilo-9.4 
Image tag          | 0.1-p1

	senza create spilo.yaml pompeii registry.opensource.zalan.do/acid/spilo-9.4:0.1-p1
	
The address in the example above contains a fully-functional image of spilo, although, you can use another one if you build the spilo image yourself and pushed it to a different docker registry.

You can now monitor the progress using:
	senza watch -n 2 DEFINITION.yaml CLUSTER_NAME
