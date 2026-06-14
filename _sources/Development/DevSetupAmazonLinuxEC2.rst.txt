Developer Setup On Amazon Linux 2023 EC2
========================================

This page is for an EC2 development VM. Production deployment should follow the
SAM/Makefile deployment flow, not ad hoc manual setup.

Base Packages
-------------

.. code-block:: bash

   sudo dnf update -y
   sudo dnf install -y git make nodejs npm python3.12 java-21-amazon-corretto-headless curl lsof zip

Install GitHub CLI if needed:

.. code-block:: bash

   sudo dnf install -y 'dnf-command(config-manager)'
   sudo dnf config-manager --add-repo https://cli.github.com/packages/rpm/gh-cli.repo
   sudo dnf install -y gh --repo gh-cli
   gh auth login

Checkout And Install
--------------------

.. code-block:: bash

   git clone https://github.com/Plant-Tracer/webapp.git webapp
   cd webapp
   make install-ubuntu

Local Development
-----------------

Use the same local-service flow as other platforms:

.. code-block:: bash

   make start-local-services
   make make-local-demo
   make run-local-lambda-debug
   make run-local-debug

HTTPS, DNS, Route 53, and certificate setup are deployment concerns and should
be handled through the current AWS deployment process for the target stack.
