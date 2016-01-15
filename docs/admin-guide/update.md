Spilo is a stateful appliance, therefore you may need to update certain componenents from time to time.
Examples of these updates are:

* Update Taupage AMI
* PostgreSQL minor upgrade (e.g. 9.4.4 to 9.4.5)
* Spilo Patch (e.g. spilo94:0.76-p1 to spilo94:0.76-p3)
* Bigger EBS volumes (e.g. 50 GB to 100 GB)

## Update the configuration
* [Senza: Updating Taupage AMI](http://stups.readthedocs.org/en/latest/user-guide/maintenance.htm    l?highlight=patch#updating-taupage-ami)
To change the configuration of Spilo you need to change the Cloud Formation Stack or the Launch Configuration of Spilo.



## Apply the configuration
This is a two step process:

* Use `senza patch` to update the Launch Configuration of Spilo
    * [Senza: Updating Taupage AMI](http://stups.readthedocs.org/en/latest/user-guide/maintenance.html?highlight=patch#updating-taupage-ami)
* Rotate the Spilo replica's
    * Terminate a Spilo replica
    * Wait for the new replica to be available and replicating
    * Repeat for other replica(s)
* [Failover Spilo](/admin-guide/failover)
* After succesfull failover: Terminate the previous master

All newly launched EC2 instances will now be using the updated Taupage AMI.
