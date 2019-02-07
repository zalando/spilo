=========================================
Spilo: HA PostgreSQL Clusters with Docker
=========================================

Spilo is a Docker image that provides PostgreSQL and `Patroni <https://github.com/zalando/patroni>`__ bundled together. Patroni is a template for PostgreSQL HA. Multiple Spilos can create a resilient High Available PostgreSQL cluster. For this, you'll need to start all participating Spilos with identical `etcd <https://github.com/coreos/etcd>`__ addresses and cluster names. 

Spilo's name derives from სპილო [spiːlɒ], the Georgian word for "elephant."  

Real-World Usage and Plans
--------------------------

Spilo is currently evolving: Its creators are working on a Postgres operator that would make it simpler to deploy scalable Postgres clusters in a Kubernetes environment, and also do maintenance tasks. Spilo would serve as an essential building block for this. There is already a `Helm chart <https://github.com/kubernetes/charts/tree/master/incubator/patroni>`__ that relies on Spilo and Patroni to provision a five-node PostgreSQL HA cluster in a Kubernetes+Google Compute Engine environment. (The Helm chart deploys Spilo Docker images, not just "bare" Patroni.)

How to Use This Docker Image
============================

Spilo's setup assumes that you've correctly configured a load balancer (HAProxy, ELB, Google load balancer) that directs client connections to the master. There are two ways to achieve this: A) if the load balancer relies on the status code to distinguish between the healthy and failed nodes (like ELB), then one needs to configure it to poll the API URL; otherwise, B) you can use callback scripts to change the load balancer configuration dynamically.

Connecting to PostgreSQL
------------------------
**Administrative Connections**

PostgreSQL is configured by default to listen to port 5432. Spilo master initializes PostgreSQL and creates the superuser and replication user (``postgres`` and ``standby`` by default).

You'll need to setup Spilo to create a database and roles for your application(s). For example:

.. code-block:: bash

    psql -h myfirstspilo.example.com -p 5432 -U admin -d postgres

**Application Connections**

Once you have created a database and roles for your application, you can connect to Spilo just like you want to connect to any other PostgreSQL cluster:

.. code-block:: bash

    psql -h myfirstspilo.example.com -p 5432 -U wow_app -d wow
    psql -d "postgresql://myfirstspilo.example.com:5432/wow?user=wow_app"

Configuration
-------------

Spilo is configured via environment variables, the values of which are either supplied manually via the environment (whenever Spilo is launched as a set of Docker containers) or added in the configuration file or manifest (whenever Spilo is used in the Docker orchestration environment, such as Kubernetes or Docker Compose).

Please go `here <https://github.com/zalando/spilo/blob/master/ENVIRONMENT.rst>`__ to see our list of environment variables.

Issues and Contributing
-----------------------

Spilo welcomes questions via our `issues tracker <https://github.com/zalando/spilo/issues>`__. We also greatly appreciate fixes, feature requests, and updates; before submitting a pull request, please visit our `contributor guidelines <https://github.com/zalando/spilo/blob/master/CONTRIBUTING.rst>`__.

License
-------

This project uses the `Apache 2.0 license <https://github.com/zalando/spilo/blob/master/LICENSE>`__. 
