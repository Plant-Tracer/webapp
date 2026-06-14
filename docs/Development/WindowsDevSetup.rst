Windows Developer Setup Notes
=============================

Windows is not a targeted runtime environment for Plant Tracer. Prefer macOS,
Ubuntu, or an Amazon Linux EC2 development VM.

If Windows must be used, use WSL2 with Ubuntu and follow
:doc:`DevSetupUbuntu`. Native Windows setup is best-effort only because local
service management, browser testing, and shell behavior are developed through
Unix-like Makefile targets.

Native Windows prerequisites, if attempted:

* Git
* GitHub CLI
* Make
* Python 3.12
* Poetry
* Node.js and npm
* Java runtime for DynamoDB Local
* Chrome or Chromium

Run validation through the same Makefile targets when possible:

.. code-block:: bash

   make lint
   make pytest
   make jscoverage
