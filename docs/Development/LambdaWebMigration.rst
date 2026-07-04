Lambda Web Migration
====================

Status
------

This is the accepted implementation plan for PR #1113 and issues #450, #699,
and #1110. The target distribution is Lambda-only: the SAM deployment path must
not create, configure, or depend on a virtual machine.

Plant Tracer still uses Flask as the web application runtime. Local Flask
development and testing remain required. SAM local testing is useful as an
additional Lambda event-routing check, but it does not replace the normal
Flask test path.

Target Architecture
-------------------

The stack has two application Lambda functions:

``lambda-web``
    Runs the existing Flask application behind API Gateway HTTP API events. It
    serves HTML pages, Flask ``/api/*`` routes, and application static files
    under ``/static/*``.

``lambda-resize``
    Remains the vision/video/tracing function. It serves ``/resize-api/*``
    routes and consumes SQS trace work. It should not become the general web
    application Lambda.

The public application should use one HTTPS front door. Separate Lambda
functions do not require separate product domain names. HTTP API route
selection should be explicit:

* ``/resize-api/*`` routes to ``lambda-resize``.
* HTML pages route to ``lambda-web``.
* Flask ``/api/*`` routes route to ``lambda-web``.
* ``/static/*`` routes to ``lambda-web`` for the initial migration.

Resize-owned browser endpoints, including movie-data, live under
``/resize-api/v1/*``. The Lambda-only target does not preserve
``/api/v1/movie-data`` as a public compatibility path.

Removed VM Surface
------------------

The Lambda-only SAM path must remove these VM-era deployment concerns:

* EC2 instance, EIP, security group, VPC/subnet/route-table, internet gateway,
  instance profile, and VM DNS resources.
* SSH, reload, and instance-log workflows from the Lambda deployment path.
* VM bootstrap scripts as a required deployment step.
* Branch selection parameters such as ``GitBranch``.
* Boot-time ``git clone`` of the application.

SAM builds and deploys the current checkout's built artifacts. The branch in
use is the branch being built, not a CloudFormation parameter.

Static Assets
-------------

Static files remain served by Flask through ``lambda-web`` for the first
Lambda-only migration. This keeps the current local Flask behavior and avoids
introducing a cache/versioning problem during the runtime migration.

Do not move application JavaScript, CSS, images, or templates to S3 or
CloudFront until there is an explicit asset-versioning plan. That later plan
should define hashed or otherwise versioned filenames, cache policy, and
rollback behavior.

S3 remains the long-lived movie and frame archive. It is an existing bucket and
must outlive the CloudFormation stack.

Data Ownership
--------------

DynamoDB tables are external to CloudFormation ownership. The stack receives
the table prefix and grants prefix-scoped permissions, but table creation and
schema maintenance remain handled by repository tooling such as
``src/dbutil.py`` and ``etc/dynamodb_tables.json``.

The migration must not make stack deletion delete the long-lived S3 archive or
the DynamoDB data model.

Local Testing
-------------

Local Flask testing remains the primary development loop:

* ``make run-local-debug`` starts the Flask app locally.
* ``make run-local-demo-debug`` starts the Flask app in local demo mode.
* ``make pytest`` runs the Python test suite against local DynamoDB and MinIO.

Lambda-specific local testing should be additive:

* ``lambda-web`` handler tests should exercise API Gateway HTTP API events
  without bypassing Flask route behavior.
* SAM local targets may provide higher-fidelity routing smoke tests for the
  built template.
* SAM local tests should not become a prerequisite for ordinary Flask route
  development unless the behavior depends on Lambda/API Gateway event shape.

Packaging Boundaries
--------------------

``lambda-web`` and ``lambda-resize`` need separate package boundaries.

``lambda-web`` should include Flask, templates, static assets, and the
application modules needed by HTML and Flask API routes. It should not include
OpenCV/PyAV/video-processing dependencies unless a later measured need appears.

``lambda-resize`` should continue to include only the video/tracing runtime and
the small app modules it already vendors for DynamoDB/S3/movie metadata work.

The Makefile is the source of truth for packaging, vendoring, tests, SAM
validation, deployment, and smoke checks.

Implementation Steps
--------------------

1. Add ``lambda-web`` with a small WSGI-to-HTTP-API adapter around the existing
   Flask app.
2. Add Makefile targets to vendor web runtime files, build ``lambda-web``
   requirements, and test the handler while preserving ``make pytest``.
3. Split SAM resources into explicit ``lambda-web`` and ``lambda-resize``
   functions on one HTTP API.
4. Remove VM parameters, resources, outputs, and VM-only deployment workflow
   hooks from the Lambda-only SAM path.
5. Preserve ``lambda-resize`` SQS trace processing and ``/resize-api/*`` routes.
6. Preserve static file serving through Flask/``lambda-web``.
7. Update deployment and smoke targets so they name the web and resize Lambda
   functions separately.
8. Run Makefile-based validation for Flask tests, Lambda handler tests, SAM
   template validation, and documentation.

Validation Requirements
-----------------------

Before PR #1113 is ready to merge, validate at least:

* existing Flask local tests still pass through ``make pytest``;
* ``lambda-web`` serves ``/ping`` or equivalent health, one static asset, and a
  representative Flask route through API Gateway event handling;
* ``lambda-resize`` still serves ``/resize-api/v1/ping`` and keeps SQS trace
  event handling;
* SAM template validation/linting passes;
* a deployed or SAM-local smoke path confirms route separation between
  ``lambda-web`` and ``lambda-resize``;
* documentation reflects the Lambda-only deployment shape and the continued
  Flask-local development workflow.
