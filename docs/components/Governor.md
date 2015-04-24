Introduction
============
Governor is the process that "governs" PostgreSQL. It uses information from PostgreSQL to determine its health. It uses etcd to determine what role this PostgreSQL instance has within the HA-cluster.
It can start, restart, promote, rebuild a PostgreSQL instance.
