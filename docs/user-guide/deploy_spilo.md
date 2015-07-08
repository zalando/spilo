Prerequisites
=============

* Have an etcd-cluster available
* Have some global idea about the usage characteristics of the appliance
* Have unique name for the cluster
* The appliction\_id `spilo` (you can change this though) needs to be registered in yourturn
* The S3 mint bucket needs to be added to the Access Control

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
Docker repository  | docker.registry.example.com
Docker image       | repository/spilo
Image tag          | 0.7-SNAPSHOT

	senza create spilo.yaml pompeii docker.registry.example.com/repository/spilo:0.7-SNAPSHOT

You can now monitor the progress using:
	senza watch -n 2 DEFINITION.yaml CLUSTER_NAME
