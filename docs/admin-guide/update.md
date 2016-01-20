Spilo is a stateful appliance, therefore you may need to update certain components from time to time.
Examples of these updates are:

* Update Taupage AMI
* PostgreSQL minor upgrade (e.g. 9.4.4 to 9.4.5)
* Spilo Patch (e.g. spilo94:0.76-p1 to spilo94:0.76-p3)
* Bigger EBS volumes (e.g. 50 GB to 100 GB)

## Update the configuration
* [Senza: Updating Taupage AMI](http://stups.readthedocs.org/en/latest/user-guide/maintenance.htm    l?highlight=patch#updating-taupage-ami)
To change the configuration of Spilo you need to change the Cloud Formation Stack or the Launch Configuration of Spilo.

The following options are available to you

**senza patch**

Use `senza patch` to update the Launch Configuration of Spilo (Taupage AMI for example).

[Senza: Updating Taupage AMI](http://stups.readthedocs.org/en/latest/user-guide/maintenance.html?highlight=patch#updating-taupage-ami)

**senza update**

If you need to change something other than the Taupage AMI, for example the Docker image, you will need
to update the Cloud Formation Template. You should use the same template you used to create this Spilo,
make the necessary changes and execute `senza update`.

**Note**: Updating the Cloud Formation Stack carries risk. If you change any infrastructure parameters (e.g.
reducing the Auto Scaling Group members), the update will force this change upon the infrastructure.

```bash
senza update spilo-tutorial.yaml <version> [PARAMETERS]
```
## New replica initialization
While you can always terminate a replica and make the autoscaling group replace it with a new one, which includes the changes made to the Cloud Formation or Autoscaling Group, the process involves a base backup from the master and might take a lot of time for large databases. Therefore, it might be more efficient to use the [EBS Snapshots](http://docs.aws.amazon.com/AWSEC2/latest/UserGuide/EBSSnapshots.html), the feature of AWS. It makes possible to bootstrap an arbitrary number of replicas without imposing any extra load on the master. Here's how to utilize them:

* Pick up an existing replica and [make a snapshot](http://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ebs-creating-snapshot.html) of its non-root EBS volume (it's usually named /dev/xvdk).
* Change the senza definition YAML:
   * Add the following line:
      ```SnapshotId: ID of the snapshot created on a previous step``` under `Ebs` block (a subblock of `BlockDeviceMappings`).
   * Set the parameter `erase_on_boot` under `mounts` (a subblock of `TaupageConfig`) to `false`.
   * Do ```senza update``` with the new definition.

This ensures that a new replica will use a snapshot taken out of an existing one and will not try to erase a data populated by the snapshot automatically during the start.

Note: usage of snapshots adds one extra step to the procedure below: 
   * Revert the snapshot-related changes in the YAML template and do `senza update` with the changed YAML one last time.

## Apply the configuration
This is a three step process:

* Rotate the Spilo replica's
    * Terminate a Spilo replica
    * Wait for the new replica to be available and replicating
    * Repeat for other replica(s)
* [Failover Spilo](/admin-guide/failover)
* After succesfull fail over: Terminate the previous master

All newly launched EC2 instances will now be using the updated Taupage AMI.
