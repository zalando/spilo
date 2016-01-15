In the lifetime of Spilo you may need to manually failover the master to a replica, some of 
these reasons are:

* Mandatory Taupage AMI update
* Scheduled AWS maintenance in your region
* Scheduled EC2 maintenance by AWS

You can trigger a failover using the api. The command line tool `patronictl` can also issue a failover (since Patroni 0.75).
Using the api to failover is the preferred method, as it will execute preliminary checks and provide feedback.

An alternative method which works with any version is to trigger an automatic failover.

* Identify the node currently running as a master (LB Status = `IN_SERVICE`)
* Request access using `piu` to the EC2 instance currently running as a master
* Stop the currently running Docker container
* Wait 10-20 seconds
* Start the previously stopped Docker container
* Verify cluster health

**Example failover (from master i-967d301b to master i-24051ead)**

```bash
user@localhost ~ $ senza instances spilo tutorial
Stack Name│Ver.     │Resource ID│Instance ID│Public IP│Private IP    │State  │LB Status     │Launched
spilo      tutorial AppServer   i-24051ead            172.31.156.138 RUNNING OUT_OF_SERVICE   8d ago
spilo      tutorial AppServer   i-482e02c3            172.31.170.155 RUNNING OUT_OF_SERVICE   8d ago
spilo      tutorial AppServer   i-967d301b            172.31.142.172 RUNNING IN_SERVICE       8d ago

user@localhost ~ $ piu 172.31.142.172 --user=aws_user "Failing over Patroni"

user@localhost ~ $ ssh -tA aws_user@odd-eu-west-1.team.example.com ssh -o StrictHostKeyChecking=no aws_user@172.31.142.172

aws_user@ip-172-31-142-172:~$ docker stop $(docker ps -q)
865347e6d41d

aws_user@ip-172-31-142-172:~$ sleep 20

aws_user@ip-172-31-142-172:~$ docker start $(docker ps -qa)
865347e6d41d

aws_user@ip-172-31-142-172:~$ logout

user@localhost ~ $ senza instances spilo tutorial
Stack Name│Ver.     │Resource ID│Instance ID│Public IP│Private IP    │State  │LB Status     │Launched
spilo      tutorial AppServer   i-24051ead            172.31.156.138 RUNNING IN_SERVICE       8d ago
spilo      tutorial AppServer   i-482e02c3            172.31.170.155 RUNNING OUT_OF_SERVICE   8d ago
spilo      tutorial AppServer   i-967d301b            172.31.142.172 RUNNING OUT_OF_SERVICE   8d ago
```
