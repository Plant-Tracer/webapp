Deploying To EC2
================

EC2 deployment is not the primary documented release path. Prefer the current
AWS SAM/Makefile deployment flow in the root ``Makefile`` and
``template.yaml``.

If an EC2 developer VM is needed, see :doc:`DevSetupAmazonLinuxEC2`.

Operational notes:

* Do not store private keys, instance IDs, public IPs, or one-off hostnames in
  this repository.
* Keep DNS, TLS certificates, and Route 53 changes in the deployment runbook or
  issue/PR that performs the deployment.
* Validate the application with ``make check`` before deploying code from an EC2
  checkout.
