Overview
========
We use PostgreSQL for this appliance because it provides a very robust RDBMS with a huge feature set. By using PostgreSQL we are also limited to its inherent limitations. One of those limitiations is that there can be only 1 master, it doesn't do multi-master replication (yet). Because of this limitation we decide to build an appliance that has 1 master cluster and n-slave clusters.

Having a single master inside this appliance means there will be a single point of failure (SPOF): the master. During an issue with the master the slaves will however be available for querying: it will not be a full outage. To reduce the impact of losing this SPOF we want to promote one of the slaves to a master as soon as is possible if we determine the master is lost.

Spilo was designed to be deployed on AWS.

Architecture: VPC
=================

	VPC                                                              
	+---------------------------------------------------------------+
	|                                                               |
	|                 etcd                                          |
	|                   O            DNS Service Record (SRV)       |
	|         +-----> O   O +-------> _etcd-server._tcp.example.com |
	|         |        O O<+                                        |
	|         |        ^   |                                        |
	|         |        |   |            +-----+                     |
	|         |        +---------------->     |                     |
	|         |  +----------------------> DDS |                     |
	|         |  |         |   +-------->     |                     |
	|         |  |         |   |        +-----+                     |
	| +--------------+  +--------------+                            |
	| |-------v------|  |--v-----------|                            |
	| ||            ||  ||            ||                            |
	| ||HA Cluster 1||  ||HA Cluster 2||                            |
	| ||            ||  ||            ||                            |
	| |--------------|  |--------------|                            |
	| +--------------+  +--------------+                            |
	|                                                               |
	+---------------------------------------------------------------+

Considerations
--------------
When considering what to build we had to determine which problems we want to solve or prevent.
The following points are important for us:

- automatic failover
- deploying a new HA-cluster can be done very quickly (< 15 minutes)
- human interaction for creating a HA-cluster is minimal
- sane defaults for a HA-cluster (security, configuration, backup)

High Available cluster (HA-cluster)
-----------------
A set of machines serving PostgreSQL databases. Its architecture is explained in more detail further on.

etcd
----
We were pointed towards etcd in combination with PostgreSQL by Compose with their [Governor](https://github.com/compose/governor). By using an external service, which is specialized in solving the problem of distributed consencus, we don't have to write our own. However, we made numeruous improvements to the Compose Governor and eventually forked it off into our own version under the name [Patroni](https://github.com/zalando/patroni). Patroni works with multiple DCSes (etcd and zookeeper, support for consul is coming up), can execute base backups asynchronously, provides a REST API for health-checks and management and contains numerous stability improvements. Patroni is the brain behind Spilo's ability to auto-failover. In our setup, Patroni works with one etcd per environment.

To find out more about etcd: [coreos.com/etcd](https://coreos.com/etcd/)

dds
---
A dynamic discovery service could be running which will gather information about the running HA-clusters. To find out which HA-clusters are running it will consult etcd.
The results of its discovery will also be stored in etcd, so other tools can easily use the discovered information.



Architecture: PostgreSQL High Available cluster
================

			   Healthcheck +-----------------------+                           
			   +-----------> Elastic Load Balancer <---+                       
			   |           +-------------+---------+   |                       
			   |                         |             |                       
			   |                         |     +-------+                       
			   |                         |     |                               
		   EC2 |nstance                  |     |  EC2 Instance                 
	+----------------------------------+ | +----------------------------------+
	|          |                       | | |   |                              |
	|          |                       | | |   |                              |
	| +--------+-+    +--------------+ | | | +-+--------+    +--------------+ |
	| |          |    |              | | | | |          |    |              | |
	| | Patroni <----> etcd (proxy) | | | |  | Patrobi <----> etcd (proxy)  | |
	| |          |    |              | | | | |          |    |              | |
	| +--------^-+    +--------------+ | | | +--------^-+    +--------------+ |
	|          |                       | | |          |                       |
	|          |                       | | |          |                       |
	|        +-v----------+            | | |        +-v----------+            |
	|        | PostgreSQL |            | | |        | PostgreSQL |            |
	|        +------------+            | | |        +------------+            |
	|        |   Master   <--------------+ |        |   Slave    |            |
	|        +------------+            |   |        +------------+            |
	|        |            |            |   |        |            |            |
	|        +------------+            |   |        +------------+            |
	|                                  |   |                                  |
	+----------------------------------+   +----------------------------------+

etcd proxy
----
We assume a Higly Available etcd-cluster to be available for spilo when it is bootstrapped; we will use a etcd-proxy running on localhost to be a bridge between a HA-cluster member and the etcd-cluster.

Patroni
----

PostgreSQL
----
We use stock PostgreSQL (9.4) packages managed by Patroni. New replicas are created from the existing master using pg_basebackup. New replication slot is registered on a master for a new replica to make sure that WAL segments required to restore it from pg_basebackup will be retained. Currently, the appliance also ships WAL segment to AWS S3 using WAL-E (this can be changed in the senza template), and is also capable of bring up replica from the base backup on S3 produced by WAL-E. Currently, S3 will only be used if the amount of WAL files archived since the latest base backup does not exceed a certain configurable threshold (10GB by default) or 30% of the base backup size, otherwise, pg_basebackup will kick in. The rationale is that we do not want to wait very long for the replica to restore all the pending WAL files, which might happen if there are too many of them.


