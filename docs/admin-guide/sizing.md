As every use case of a database is unique we cannot simply advise you to use a certain instance type for Spilo.
To get some notion of what is available, look at the Amazon resources:

* [Amazon EC2 Instances](https://aws.amazon.com/ec2/instance-types/)

# Guidelines
We can however provide some guidelines in choosing your instance types.
Choosing an instances type has some basic parameters:

- database size
- database usage pattern
- performance requirements
- usage characteristics
- costs

## Costs
To have some notion of the costs of Spilo, we have calculated the costs for some possible configurations.

**Note**: These are costs for an single Spilo deployment, as a case study. All prerequisites (Senza, Etcd) are considered
to be available and are not part of the costs of Spilo.
These figures are meant to show the approximate costs, they *will* vary depending on your use case and resource usage.


The following table shows ballpark figures of the raw costs of a Spilo deployment in 3 Availability Zones.
The pricing information is taken from Amazon with their calculator (January 2016).

* [Amazon EC2 Pricing](https://aws.amazon.com/ec2/pricing/)
* [Amazon EBS Pricing](https://aws.amazon.com/ebs/pricing/)
* [Amazon ELB Pricing](https://aws.amazon.com/elasticloadbalancing/pricing/)

**Monthly costs for a Spilo with 3 nodes**

| EC2   |   Storage                     | On-Demand ($) | 1 Yr All Upfront ($) | 3 Yr All Upfront ($) |
|----------|---------------------------:|---------:|-------:|----:|
| t2.micro |  10 GB EBS                 |      74 | 64 | 57 |
| m4.large | 100 GB EBS                 |    371 | 370 | 308 |
| r3.2xlarge | (provisioned) 500 GB EBS |   2164 | 1500 | 978 |
| d2.8xlarge | (RAID 10) 24 TB HDD      |  14244 | 7253 | 4970 |

**Note**: When choosing All Upfront you can reduce your monthly costs considerably, yet an AWS Support plan is necessary.
Support costs are included in these numbers, these may be much lower if you already buy support from AWS.

Do your own calculations on the [Amazon Simple Monthly Calculator](http://calculator.s3.amazonaws.com/index.html)

## Database usage
For some types of databases the smallest possible instance available can be a good candidate. Some examples that
can probably run fine on t2.micro instances are:

* Very small (< 500 MB) databases
* Databases which are not queried often or heavily (some configuration store, an application registry)
* Proof of Concepts / Prototyping


