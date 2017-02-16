## Spilo: HA PostgreSQL Clusters with Docker

Spilo is a Docker image that provides a resilient, High Available PostgreSQL cluster (HA-cluster) that you can configure and start within minutes. Spilo can run several clusters at one time, with one cluster acting as a master and the others as slaves. Its name derives from სპილო [spiːlɒ], the Georgian word for "elephant." 

Spilo is currently evolving: Its creators are working on a Postgres operator that would make it simpler to deploy scalable Postgres clusters in a Kubernetes environment, and do maintenance tasks. Spilo would serve as an essential building block for this.

Spilo works in combination with [Patroni](https://github.com/zalando/patroni), a template for PostgreSQL HA. Patroni works with [etcd](https://coreos.com/etcd/), [ZooKeeper](https://zookeeper.apache.org/) or [Consul](https://www.consul.io/), and manages the [PostgreSQL](https://www.postgresql.org) databases running in your Spilo cluster. It ensures that there is only one master within your Spilo. (It's worth noting here that Patroni includes a Helm Chart that enables you to deploy a five-node Patroni cluster using a Kubernetes PetSet, in a Google Compute Engine environment.)

###How to Use This Docker Image

First, there are some technical requirements:
- A Distributed Configuration Store (DCS), to allow distributed nodes to agree. Most Patroni deployments use etcd, which implements the [Raft protocol](https://github.com/coreos/etcd/tree/master/raft). For more information about Raft, visit [this resource](http://thesecretlivesofdata.com/raft/) and check out [this interactive visualization](https://raft.github.io).

>>>**not sure if this is correct?** This image includes 5432 (the Postgres port). The default Postgres user and database are created in the entrypoint with initdb.

#### Administrative Connections//[could this be put as "Connecting to Postgres"?]

You'll need to setup Spilo to create a database and roles for your application(s). For example:

    psql -h myfirstspilo.example.com -p 5432 -U admin -d postgres

#### Application Connections

Once you have created a database and roles for your application, you can connect to Spilo just like you want to connect to any other PostgreSQL cluster:

    psql -h myfirstspilo.example.com -p 5432 -U wow_app -d wow
    "postgresql://myfirstspilo.example.com:5432/wow?user=wow_app"

#### Connecting to Other Containers

#### Environment Variables
#### Supported Tags and Respective Dockerfile Links
#### How to Extend This Image

### Connect to a Spilo Appliance
This should be the same as connecting to a PostgreSQL database or an RDS instance. Use the dns-name you specified during creation as the hostname, and use your credentials to authenticate.

### Issues

### Contributing
Spilo welcomes questions via our [Issues](https://github.com/zalando/spilo/issues). We also greatly appreciate fixes, feature requests, and updates; before submitting a pull request, please visit our contributor guidelines[link TK].

### License
This project uses the [Apache 2.0 license](https://github.com/zalando/spilo/blob/master/LICENSE). 
