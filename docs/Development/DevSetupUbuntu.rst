Setting Up Plant Tracer On Ubuntu 24.04
=======================================

Install OS packages:

.. code-block:: bash

   sudo apt update
   sudo apt upgrade
   sudo apt install git gh make curl lsof nodejs npm zip chromium-browser chromium-chromedriver openjdk-21-jre-headless ffmpeg

Install Poetry if it is not already available, then clone and install:

.. code-block:: bash

   git clone https://github.com/Plant-Tracer/webapp.git webapp
   cd webapp
   make install-ubuntu

Local Run
---------

.. code-block:: bash

   make start-local-services
   make make-local-demo
   make run-local-lambda-debug
   make run-local-debug

``run-local-debug`` prints a login link for the local admin user and starts
Flask on ``http://localhost:8080``. Keep ``run-local-lambda-debug`` running in a
second terminal for first-frame, playback URL, and retrace endpoints.

Validation
----------

.. code-block:: bash

   make lint
   make pytest
   make jscoverage
   make check

Cleanup
-------

.. code-block:: bash

   make stop-local-services
   make delete-local

See :doc:`DeveloperSetup` and :doc:`Local Development and Github Actions` for
the complete local architecture.
