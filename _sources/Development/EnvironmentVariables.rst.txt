Environment Variables
=====================

This page lists runtime variables used by the current Flask app, local services,
mailer, and lambda-resize code. The Makefile supplies the local defaults for
normal development and testing.

Required
--------

``DYNAMODB_TABLE_PREFIX``
   Prefix added to every DynamoDB table name. Local defaults use ``demo-``.

``PLANTTRACER_S3_BUCKET``
   Existing S3 bucket name. Do not include ``s3://``. For local MinIO the
   Makefile uses ``planttracer-local``.

AWS And Local Service Selection
-------------------------------

``AWS_REGION``
   AWS region. Use ``local`` for DynamoDB Local and MinIO.

``AWS_DEFAULT_REGION``
   Optional AWS SDK default region. Local Make targets set this to ``local``.

``AWS_ACCESS_KEY_ID`` / ``AWS_SECRET_ACCESS_KEY``
   AWS credentials. Local MinIO uses ``minioadmin`` / ``minioadmin``.

``AWS_ENDPOINT_URL_DYNAMODB``
   DynamoDB endpoint override. Local default: ``http://localhost:8000/``.

``AWS_ENDPOINT_URL_S3``
   S3 endpoint override. Local default: ``http://localhost:9000/``.

``AWS_ENDPOINT_URL_SQS``
   Optional SQS endpoint override for lambda-resize if testing against an SQS
   emulator.

``AWS_PROFILE``
   Optional AWS profile for deployed or administrative commands.

Application URLs
----------------

``PLANTTRACER_API_BASE``
   Optional Flask API base injected into browser pages as ``API_BASE``. Empty
   means same-origin.

``PLANTTRACER_STATIC_BASE``
   Optional static asset base injected as ``STATIC_BASE``.

``PLANTTRACER_LAMBDA_API_BASE``
   Explicit lambda-resize HTTP API base injected as ``LAMBDA_API_BASE``. Local
   default from the Makefile is ``http://127.0.0.1:9811/``.

``HOSTNAME`` / ``DOMAIN``
   If ``PLANTTRACER_LAMBDA_API_BASE`` is absent, Flask derives
   ``https://{HOSTNAME}-lambda.{DOMAIN}/``.

Demo Mode
---------

``DEMO_MODE``
   Enables demo mode when present.

``DEMO_COURSE_ID``
   Identifies the course containing demo data. This does not enable demo mode by
   itself.

Mail
----

``SERVER_EMAIL``
   Sender address for outgoing mail. Defaults to ``admin@planttracer.com``.

``PLANTTRACER_CREDENTIALS``
   Path to an INI file with ``[smtp]`` and optional ``[imap]`` sections.

``SMTPCONFIG_JSON``
   JSON SMTP configuration. Local Make targets set this for Mailpit.

``SMTPCONFIG_ARN``
   AWS Secrets Manager ARN containing SMTP configuration.

``MAILER_DRY_RUN``
   Set to ``true`` to log email content instead of sending it.

Lambda Queue
------------

``TRACKING_QUEUE_MODE``
   Set to ``local`` to use the in-process local retrace queue.

``TRACKING_QUEUE_URL``
   SQS queue URL used by deployed lambda-resize tracking.

Development And Diagnostics
---------------------------

``LOG_LEVEL``
   Logging level. Local Make targets default to ``DEBUG``.

``FFMPEG_PATH``
   Optional path used by legacy/local tooling.

``COLLECT_JS_COVERAGE``
   When true, Flask serves instrumented static files from
   ``static-instrumented`` if present.

``DISABLE_PROXYFIX``
   When true, disables Flask ``ProxyFix`` handling for forwarded headers.

``AWS_EC2_METADATA_DISABLED``
   Local Make targets set this to ``true`` to avoid AWS metadata lookups.

Local Makefile Defaults
-----------------------

The primary local environment is defined by ``LOCAL_AWS_ENV`` and
``LOCAL_FLASK_ENV`` in the root Makefile. Prefer these targets over hand-built
commands:

.. code-block:: bash

   make start-local-services
   make make-local-demo
   make run-local-debug
   make run-local-demo-debug
   make run-local-lambda-debug
