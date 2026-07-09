Developer Setup
===============

Requirements
------------

* Python 3.12
* Poetry
* Node.js and npm
* Java runtime for DynamoDB Local
* Git and GitHub CLI (``gh``)
* Chrome or Chromium for browser tests
* Make

Use the platform-specific setup pages for OS package details:

* :doc:`DeveloperSetup_Mac`
* :doc:`DevSetupUbuntu`
* :doc:`WindowsDevSetup`

Clone And Install
-----------------

.. code-block:: bash

   git clone https://github.com/Plant-Tracer/webapp.git webapp
   cd webapp
   make install-macos      # macOS
   make install-ubuntu     # Ubuntu

The Makefile creates an in-project Poetry environment at ``.venv``.

Local Services
--------------

Start all local services:

.. code-block:: bash

   make start-local-services

This starts:

* DynamoDB Local on ``http://localhost:8000/``
* MinIO on ``http://localhost:9000/``
* Mailpit on ``http://localhost:8025/`` for the web UI and port ``1025`` for SMTP

Seed local data:

.. code-block:: bash

   make make-local-demo

Storage Modes
-------------

The local checkout can run against either local storage emulators or remote AWS
storage. Pick one mode per shell.

Local storage mode is the default. Leave ``AWS_REGION`` unset, or set it to
``local``. The Makefile sets DynamoDB Local and MinIO endpoint overrides,
``PLANTTRACER_S3_BUCKET=planttracer-local``, and
``DYNAMODB_TABLE_PREFIX=demo-``:

.. code-block:: bash

   make show-storage-mode
   make start-local-services
   make make-local-demo
   make run-local-lambda-debug
   make run-local-debug

Remote storage mode runs local Flask and, if needed, the local lambda debug
bridge against real AWS S3 and DynamoDB. Use this only with a development
bucket and table prefix unless you explicitly intend to modify shared data.
The Makefile requires the remote storage settings to be explicit and unsets
local endpoint overrides for the remote debug targets:

.. code-block:: bash

   AWS_PROFILE=plantadmin \
   AWS_REGION=us-east-1 \
   PLANTTRACER_S3_BUCKET=planttracer-dev \
   DYNAMODB_TABLE_PREFIX=dev- \
   make show-storage-mode

   AWS_PROFILE=plantadmin \
   AWS_REGION=us-east-1 \
   PLANTTRACER_S3_BUCKET=planttracer-dev \
   DYNAMODB_TABLE_PREFIX=dev- \
   make run-remote-lambda-debug

   AWS_PROFILE=plantadmin \
   AWS_REGION=us-east-1 \
   PLANTTRACER_S3_BUCKET=planttracer-dev \
   DYNAMODB_TABLE_PREFIX=dev- \
   make run-remote-debug

Do not run ``make make-local-demo`` for remote storage mode. That target is
intentionally tied to DynamoDB Local and MinIO.

Run Locally
-----------

Normal local development uses two processes:

.. code-block:: bash

   make run-local-lambda-debug
   make run-local-debug

``run-local-debug`` starts Flask on ``http://localhost:8080`` in non-demo mode
and prints a local admin login link. On macOS it also attempts to open the
local Lambda debug process automatically.

Demo mode:

.. code-block:: bash

   make run-local-demo-debug

Validation
----------

Use the Makefile entry points:

.. code-block:: bash

   make lint
   make pytest
   make jscoverage
   make check

Do not bypass the Makefile for normal testing. The Makefile sets the local AWS,
DynamoDB, MinIO, Mailpit, and Python path environment needed by tests.

Create A Course
---------------

.. code-block:: bash

   AWS_REGION=local poetry run python src/dbutil.py create-course \
     --course_name "Test Course" \
     --course_id "test" \
     --admin_email admin@example.com \
     --admin_name "Admin User"

For most local development, prefer ``make make-local-demo`` and the login link
printed by ``make run-local-debug``.

Cleanup
-------

.. code-block:: bash

   make stop-local-services
   make delete-local
   make wipe-local

``delete-local`` stops services and removes local artifacts. ``wipe-local``
removes local artifacts, restarts services, and recreates the local bucket.
