Introduction
============
Spilo (სფილო, small elephants) is a Highly Available PostgreSQL cluster (HA-cluster). It will run a number of clusters with one cluster being a master and the others being slaves. Its purpose is to provide a very resilient, highly available PostgreSQL cluster which can be configured and started within minutes.

Design
======

Overview
--------
We use PostgreSQL for this appliance because it provides a very robust RDBMS with a huge feature set. By using PostgreSQL we are also limited to its inherent limitations. One of those limitiations is that there can be only 1 master, it doesn't do multi-master replication (yet). Because of this limitation we decide to build an appliance that has 1 master cluster and n-slave clusters.

Having a single master inside this appliance means there will be a single point of failure (SPOF): the master. During an issue with the master the slaves will however be available for querying: it will not be a full outage. To reduce the impact of losing this SPOF we want to promote one of the slaves to a master as soon as is possible if we determine the master is lost.

Spilo was designed to be deployed on AWS.

Architecture: VPC
-----------------




Architecture: PostgreSQL High Available cluster
-----------------------------------------------

							+-----------------------+
							| Elastic Load Balancer |
							+-----------+-----------+
										|
								+-------+----------------------------+
	 EC2 Instance				|          EC2 Instance              |
	+--------------------------------+    +--------------------------------+
	|                           |    |    |                          |     |
	|  +--------------+         |    |    |  +--------------+        |     |
	|  |              |         |    |    |  |              |        |     |
	|  | etcd (proxy) |         |    |    |  | etcd (proxy) |        |     |
	|  |              +----+    |    |    |  |              +----+   |     |
	|  +--^-----------+    |    |    |    |  +--^-----------+    |   |     |
	|     |                |    |    |    |     |                |   |     |
	|     |                |    |    |    |     |                |   |     |
	|     |                |    |    |    |     |                |   |     |
	|  +--v-------+      +-v----v--+ |    |  +--v-------+      +-v---v---+ |
	|  |          |      |         | |    |  |          |      |         | |
	|  | Governor |      | HAProxy | |    |  | Governor |      | HAProxy | |
	|  |          |      |         | |    |  |          |      |         | |
	|  +--+-------+      +-+-------+ |    |  +--+-------+      +-+-------+ |
	|     |                |         |    |     |                |         |
	|     |                |         |    |     |                |         |
	|     |                |         |    |     |                |         |
	| +---v--------+       |         |    | +---v--------+       |         |
	| | PostgreSQL |       |         |    | | PostgreSQL |       |         |
	| +------------+       |         |    | +------------+       |         |
	| |   Slave    |       +---------------->   Master   <-------+         |
	| +------------+                 |    | +------------+                 |
	| |            |                 |    | |            |                 |
	| +------------+                 |    | +------------+                 |
	|                                |    |                                |
	+--------------------------------+    +--------------------------------+



etcd
----
We were pointed towards etcd in combination with PostgreSQL by compose with their [governor](https://github.com/compose/governor). By using an external service which is specialized in solving the problem of distributed consencus we don't have to write our own.

We assume a Higly Available etcd-cluster to be available for spilo when it is bootstrapped; we will use a etcd-proxy running on localhost to be a bridge between a HA-cluster member and the etcd-cluster.

HAProxy
-------

Governor
--------

PostgreSQL
----------


