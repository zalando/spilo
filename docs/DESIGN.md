# Overview
We use PostgreSQL for this appliance because it provides a very robust RDBMS with a huge feature set.
By using PostgreSQL we are also bound to its inherent limitations. One of those limitiations is that there can be only
1 master, it doesn't do multi-master replication (yet). Because of this limitation we decide to build an appliance that
has 1 master cluster and n-slave clusters.

Having a single master inside this appliance means there will be a single point of failure (SPOF): the master itself.
During an issue with the master the slaves will however be available for querying: it will not be a full outage. To
reduce the impact of losing this SPOF we want to promote one of the slaves to a master as soon as possible once we
determine the master is lost.

Spilo was designed to be deployed on AWS.

# Architecture: VPC

## Considerations
--------------
When considering what to build we had to determine which problems we want to solve or prevent.
The following points are important for us:

- automatic failover
- deployment of a new HA-cluster can be done very quickly (< 15 minutes)
- human interaction for creating a HA-cluster is minimal
- sane defaults for a HA-cluster (security, configuration, backup)

## High Available cluster (HA-cluster)
-----------------
A set of machines serving PostgreSQL databases. Its architecture is explained in more detail further on.

## PostgreSQL
----
We use stock PostgreSQL (9.4) packages managed by Patroni. New replicas are created from the existing master using pg_basebackup. New replication slot is registered on a master for a new replica to make sure that WAL segments required to restore it from pg_basebackup will be retained. Currently, the appliance also ships WAL segment to AWS S3 using WAL-E (this can be changed in the senza template), and is also capable of bring up replica from the base backup on S3 produced by WAL-E. Currently, S3 will only be used if the amount of WAL files archived since the latest base backup does not exceed a certain configurable threshold (10GB by default) or 30% of the base backup size, otherwise, pg_basebackup will kick in. The rationale is that we do not want to wait very long for the replica to restore all the pending WAL files, which might happen if there are too many of them.


