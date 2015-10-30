Deploying etcd should be a once in a VPC-lifetime thing. We can use `senza` to deploy the etcd appliance.
You can skip deploying if you already have a etcd cluster running.

The following prerequisites need to be met.

* `stups-senza`
* A [Senza Definition](http://stups.readthedocs.org/en/latest/components/senza.html#senza-definition)
* A template can be found here: [etcd-appliance.yaml](https://github.com/zalando/stups-etcd-cluster/blob/master/etcd-cluster.yaml)

To deploy the etcd-appliance, use the following:

	senza create DEFINITION.yaml VERSION HostedZone=<HOSTED_ZONE> DockerImage=<DOCKER_IMAGE> ScalyrAccountKey=<SCALAR_KEY>

For a current view of available Docker images, look at the Docker registry with your own tooling.
We advise not to use a `SNAPSHOT` or `latest` version, as they are mutable.

[https://registry.opensource.zalan.do/v1/repositories/acid/etcd-cluster/tags](https://registry.opensource.zalan.do/v1/repositories/acid/etcd-cluster/tags)

This will create and execute a cloud formation template for you.

Example:

Argument   		   | Value
-------------------|-------
Definition         | etcd-appliance.yaml
Hosted zone 	   | team.example.com
Version 		   | release
Docker repository  | registry.opensource.zalan.do
DockerImage       | acid/etcd-cluster
Image tag          | 2.2.1-p6
Scalyr Key         | mykey

	senza create etcd-cluster.yaml release HostedZone=team.example.com DockerImage=registry.opensource.zalan.do/acid/etcd-cluster:2.2.1-p6 ScalyrAccountKey=mykey

The etcd appliance will create 2 dns-records within the specified HostedZone, they will reflect changes within
the cluster:

- `_etcd-server._tcp.<Version>.<HostedZone>`  a `SRV` record for discovery purposes
- `etcd-server.<Version>.<HostedZone>`: an `A` record 

If you want your own specific dns-record to point to etcd, create a `CNAME` which points to the `A` record.
