# Scaling up or down

At some point during the lifetime of Spilo you may decide that you may need to scale up, scale down or change other
parts of the infrastructure.

The following plan will accomplish this:

1. Change the CloudFormation template to reflect the changes in infrastructure
2. Increase the number of EC2 instances in your AutoScalingGroup (or: Terminate one of the streaming replica's)
3. Kill one of the replica's running on the old configuration
4. Repeat step 2 and 3 until all replica's are running the new configuration
5. Fail over the Spilo cluster
6. Terminate the replica (the previous master)

Only during the fail over will there be some downtime for the master instance.

If your databases' size is significant, these steps may take some time to complete. Optimizations of this process
(think of using EBS snapshots) are on the roadmap but not yet available.

