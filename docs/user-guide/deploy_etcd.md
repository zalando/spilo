Deploying etcd should be a once in a VPC-lifetime thing. We can use `senza` to deploy the etcd appliance.
You can skip deploying if you already have a etcd cluster running.

The following prerequisites need to be met.

* `stups-senza`
* A [Senza Definition](http://stups.readthedocs.org/en/latest/components/senza.html#senza-definition)
* A template can be found here: [etcd-appliance.yaml](https://github.com/zalando/spilo/blob/master/etcd-cluster-appliance/etcd-cluster.yaml)
* The Security Group defined in the Senza Definition needs to be created

To deploy the etcd-appliance, use the following:

	senza create DEFINITION.yaml VERSION HOSTED_ZONE DOCKER_IMAGE

This will create and execute a cloud formation template for you.

Example:

Argument   		   | Value
-------------------|-------
Definition         | etcd-appliance.yaml
Hosted zone 	   | repository.example.com
Version 		   | 1
Docker repository  | docker.registry.example.com
Docker image       | repository/etcd-appliance
Image tag          | 0.2-SNAPSHOT

	senza create etcd-cluster.yaml 1 repository.example.com docker.registry.example.com/repository/etcd-appliance:0.2-SNAPSHOT
