==================================
Spilo: HA PostgreSQL Clusters with Docker
==================================

Spilo is a Docker image that provides PostgreSQL and `Patroni <https://github.com/zalando/patroni>`__ bundled together. Patroni is a template for PostgreSQL HA. Multiple Spilos can create a resilient High Available PostgreSQL cluster. For this, you'll need to start all participating Spilos with `etcd <https://github.com/coreos/etcd>`__ and cluster name parameters. Spilo's name derives from სპილო [spiːlɒ], the Georgian word for "elephant."  

Spilo is currently evolving: Its creators are working on a Postgres operator that would make it simpler to deploy scalable Postgres clusters in a Kubernetes environment, and also do maintenance tasks. Spilo would serve as an essential building block for this.

How to Use This Docker Image
============================

Spilo requires a load balancer (HAProxy, ELB, Google load balancer) to point to the master node. It provides two ways to achieve this: either by using the API URLs, or via the callback scripts. See Patroni for more details.

Connecting to PostgreSQL
------------------------
**Administrative Connections**

PostgreSQL is configured by default to listen to port 5432. The default Postgres user and database are created in the entrypoint with initdb.

You'll need to setup Spilo to create a database and roles for your application(s). For example:

    psql -h myfirstspilo.example.com -p 5432 -U admin -d postgres

**Application Connections**

Once you have created a database and roles for your application, you can connect to Spilo just like you want to connect to any other PostgreSQL cluster:

    psql -h myfirstspilo.example.com -p 5432 -U wow_app -d wow
    "postgresql://myfirstspilo.example.com:5432/wow?user=wow_app"

Environment Variables
---------------------

Please go `here <hURL TO COME>`__ to see our list.

Connect to a Spilo Appliance
--------------------------------

This should be the same as connecting to a PostgreSQL database or an RDS instance. Use the dns-name you specified during creation as the hostname, and use your credentials to authenticate.

Issues and Contributing
-----------------------

Spilo welcomes questions via our `issues tracker <https://github.com/zalando/spilo/issues>`__. We also greatly appreciate fixes, feature requests, and updates; before submitting a pull request, please visit our `contributor guidelines <https://github.com/zalando/spilo/blob/master/CONTRIBUTING.rst>`__.

License
-------

This project uses the `Apache 2.0 license <https://github.com/zalando/spilo/blob/master/LICENSE>`__. 
