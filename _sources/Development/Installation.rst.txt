Installation
============

This page covers a local or VM checkout. AWS deployment details live in the SAM
targets in the root Makefile and related deployment docs.

Repository Checkout
-------------------

.. code-block:: bash

   git clone https://github.com/Plant-Tracer/webapp.git webapp
   cd webapp

Install Dependencies
--------------------

Use the Makefile target for your platform:

.. code-block:: bash

   make install-ubuntu
   make install-macos

The Makefile installs Python dependencies with Poetry into ``.venv`` and runs
``npm ci`` for JavaScript dependencies.

Local Application
-----------------

.. code-block:: bash

   make start-local-services
   make make-local-demo
   make run-local-debug

Flask runs on ``http://localhost:8080``. lambda-resize runs locally on
``http://127.0.0.1:9811`` when started by ``make run-local-lambda-debug`` or by
``make run-local-debug`` on macOS.

Non-Demo Course
---------------

Create a course with ``dbutil``:

.. code-block:: bash

   AWS_REGION=local poetry run python src/dbutil.py create-course \
     --course_name "My Course Name" \
     --course_id "Plant101" \
     --admin_email your_admin_email@example.com \
     --admin_name "Your Name"

``dbutil`` prints the generated course key. Give that key to students so they
can register.

Mailer Configuration
--------------------

Local development uses Mailpit through ``SMTPCONFIG_JSON`` set by the Makefile.
For a real mailer, provide one of:

* ``PLANTTRACER_CREDENTIALS`` pointing at an INI file with ``[smtp]``.
* ``SMTPCONFIG_JSON`` with SMTP settings.
* ``SMTPCONFIG_ARN`` pointing at an AWS Secrets Manager secret.

Example INI section:

.. code-block:: ini

   [smtp]
   SMTP_USERNAME=plantadmin@example.com
   SMTP_PASSWORD=secret
   SMTP_PORT=587
   SMTP_HOST=smtp.example.com

Validation
----------

.. code-block:: bash

   make lint
   make pytest
   make jscoverage
   make check
