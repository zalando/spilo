In the lifetime of Spilo you may need to manually failover the master to a replica, some of 
these reasons are:

* Mandatory Taupage AMI update
* Scheduled AWS maintenance in your region
* Scheduled EC2 maintenance by AWS

## Patroni >= 0.75



## Patroni < 0.75

* Failover Spilo
    * Request access using `piu` to the EC2 instance currently running as a master
    * When using Patroni >= 0.75:
        * ssh into the EC2 instance
        * Failover using `docker exec -ti $(docker ps -q) patronictl failover`
    * When using Patroni < 0.75:
        * 
        docker stop $(docker ps -q)

All newly launched EC2 instances will now be using the updated Taupage AMI.
