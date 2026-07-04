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
   means same-origin. If set, include a complete origin/base path; the runtime
   normalizes a missing trailing slash.

``PLANTTRACER_STATIC_BASE``
   Reserved for a future versioned-asset plan. Static assets are currently
   served same-origin by Flask/``lambda-web`` under ``/static/*``.

``PLANTTRACER_LAMBDA_API_BASE``
   Explicit lambda-resize HTTP API base injected as ``LAMBDA_API_BASE``. Local
   debug targets set this to ``http://127.0.0.1:9811/`` when the local lambda
   debug bridge is running. Set it to an explicit empty value to run
   Flask-only browser tests without probing a resize service. The Lambda-only
   stack sets this to the same public application origin.

``HOSTNAME`` / ``DOMAIN``
   If ``PLANTTRACER_LAMBDA_API_BASE`` is absent, Flask derives
   ``https://{HOSTNAME}.{DOMAIN}/``. If those are also absent, Flask uses the
   current request origin.

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
   In the Lambda-only stack this is set by the stack to
   ``admin@planttracer.com`` and the Lambda role is scoped to that SES sender.
   The exact address must be verified in AWS SES in the deployment region.

``PLANTTRACER_CREDENTIALS``
   Path to an INI file with ``[smtp]`` and optional ``[imap]`` sections. Used
   for local or legacy VM-style SMTP configuration, not by the Lambda-only SAM
   stack.

``SMTPCONFIG_JSON``
   JSON SMTP configuration. Local Make targets set this for Mailpit.

``SMTPCONFIG_ARN``
   AWS Secrets Manager ARN containing SMTP configuration. The mailer supports
   this explicit override, but the Lambda-only SAM stack does not set it and
   does not grant Secrets Manager access by default. Lambda production mail uses
   SES IAM permissions instead of committed or environment-injected SMTP
   secrets.

``MAILER_DRY_RUN``
   Set to ``true`` to log email content instead of sending it. The Lambda-only
   stack exposes this as the ``MailerDryRun`` SAM parameter for non-production
   stacks whose operators cannot send SES mail as ``admin@planttracer.com``.
   Dry-run mail includes login links and API keys in Lambda logs, so use it
   only with test users and test data.

Lambda Queue
------------

``TRACING_QUEUE_MODE``
   Set to ``local`` to use the in-process local retrace queue.

``TRACING_QUEUE_URL``
   SQS queue URL used by deployed lambda-resize tracing.

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
