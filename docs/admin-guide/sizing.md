# Sizing your Spilo

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

**Note**: These are costs for an individual instance, as a case study. All prerequisites (Senza, Etcd) are considered 
to be available and are not part of the costs of Spilo.
These figures are meant to show the approximate costs, they *will* vary depending on your usecase and resource usage.

The following table shows ballpark figures of the raw costs of a single node of Spilo, as well as the Spilo costs when
using the default configuration of 3 members in the AutoScalingGroup.
The pricing information is taken from Amazon, and are for On-Demand pricing (August 2015):

* [Amazon EC2 Pricing](https://aws.amazon.com/ec2/pricing/)
* [Amazon EBS Pricing](https://aws.amazon.com/ebs/pricing/)

| EC2   |   Storage                     |  Monthly ($) | Spilo ($) |
|----------|---------------------------:|---------:|-------:
| t2.micro |  10 GB EBS                 |   11     |    33 |
| m4.large | 100 GB EBS                 |  111     |   333 |
| r3.2xlarge | (provisioned) 500 GB EBS |  664     |  1992 |
| d2.8xlarge | (RAID 10) 24 TB HDD      | 4292     | 12876 |

## Database usage
For some types of databases the smallest possible instance available can be a good candidate. Some examples that
can probably run fine on t2.micro instances are:

* Very small (< 500 MB) databases 
* Databases which are not queried often or heavily (some configuration store, an application registry)
* Proof of Concepts / Prototyping


