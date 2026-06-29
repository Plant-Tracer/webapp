Lambda Web Migration Discussion
===============================

Status
------

This is a design discussion for deprecating the existing production VM and
moving the Plant Tracer web application to AWS Lambda. It is not an
implementation plan that has already been approved.

The current deployed architecture is split:

* Flask on the VM serves HTML pages and metadata APIs.
* ``lambda-resize`` serves video/frame/tracking APIs and SQS tracking work.
* S3 stores movies and generated artifacts.
* DynamoDB stores users, courses, API keys, movie metadata, trackpoints, and
  audit logs.

The proposed target keeps S3 and DynamoDB as the durable data stores, keeps
``lambda-resize`` for video work, and adds a separate Lambda for the web
application.

Recommended Direction
---------------------

Add a new ``lambda-web`` function for the Flask HTML and metadata API runtime.
Do not merge this work into ``lambda-resize``.

Serve immutable static assets from S3, preferably behind the same front door as
the web app. Continue to serve authenticated and per-user HTML from the web
Lambda until those pages are deliberately converted into a static shell plus
client-side API calls.

Keep VM operation during and after the migration. VM support should be a
deployment/debugging mode, not a second application with divergent behavior.
The same Flask route code should run in both VM and Lambda-web modes whenever
practical.

Decision 1: Current Lambda Or New Lambda
----------------------------------------

Recommendation: create a new Lambda, tentatively named ``lambda-web``.

Pros
~~~~

* Keeps OpenCV, PyAV, and video-processing dependencies out of the web request
  path.
* Lets the web Lambda use lower memory, shorter timeout, and a smaller package
  than ``lambda-resize``.
* Keeps video/tracking scaling separate from normal page and metadata traffic.
* Lets deployment, rollback, logging, and alarms distinguish web failures from
  tracking failures.
* Preserves the existing ``lambda-resize`` API while the web runtime is moved.

Cons
~~~~

* Adds another function, IAM role, log group, custom domain or route, and smoke
  test.
* Requires a clean shared-code packaging story so Flask, ``lambda-web``, and
  ``lambda-resize`` do not drift.
* Adds URL configuration that must remain consistent across browser globals:
  ``API_BASE``, ``STATIC_BASE``, and ``LAMBDA_API_BASE``.
* Requires a decision about whether both Lambdas share one HTTP API, separate
  HTTP APIs, or a CloudFront distribution with multiple origins.

Implementation Consequences
~~~~~~~~~~~~~~~~~~~~~~~~~~~

The first implementation should prefer wrapping the existing Flask app for
Lambda HTTP API events over rewriting all Flask routes into a new router. That
keeps the first migration focused on runtime and deployment behavior rather
than route semantics.

This introduces a separate packaging target that includes the Flask web
dependencies but excludes video-processing dependencies. The dependency groups
should make that boundary explicit.

Decision 2: Static Pages And Assets From Lambda Or S3
-----------------------------------------------------

Recommendation: serve static assets from S3, but keep dynamic HTML in
``lambda-web`` initially.

Plant Tracer has three different categories that should not be collapsed into
one decision:

* Immutable assets: JavaScript, CSS, images, favicon, and vendored browser
  files. These should move to S3.
* Public static pages: pages such as terms, privacy, and about could move to S3
  only if they no longer depend on per-request navigation, demo-mode state, or
  server-injected globals.
* Dynamic pages: pages such as upload, list, analyze, users, audit, login, and
  registration still need server-rendered state today and should remain served
  by the web Lambda.

Pros Of S3 Static Assets
~~~~~~~~~~~~~~~~~~~~~~~~

* Reduces web Lambda traffic and cold-start work.
* Gives browser assets long cache lifetimes independent of API deployment.
* Makes static delivery cheaper and simpler than serving bytes through Flask.
* Fits the existing ``PLANTTRACER_STATIC_BASE`` mechanism.

Cons And Risks
~~~~~~~~~~~~~~

* Current templates use ``url_for('static', ...)`` and inject per-user browser
  globals from ``base.html``. Public pages that extend ``base.html`` are not
  purely static today.
* If S3 assets are served from a different origin, CORS, cookie, and API URL
  behavior must be tested deliberately.
* Cache invalidation needs a versioning strategy. A stale JavaScript file can
  break active pages after a Lambda deployment.
* Static docs and app assets have different lifecycles and should not be mixed
  accidentally.

Open Subdecision
~~~~~~~~~~~~~~~~

Choose the front door:

* S3 static domain plus API Gateway custom domains is simpler to build, but it
  makes cross-origin behavior more visible.
* CloudFront with S3 and API Gateway origins is more infrastructure, but can
  keep browser-visible paths under one host and gives better cache control.

Decision 3: Continue Supporting VM Operation
--------------------------------------------

Recommendation: yes. Keep VM operation as a supported debug and fallback mode.

The application should expose its runtime mode explicitly, but business logic
should not branch on that mode except where deployment-specific URLs or
diagnostics require it.

Suggested configuration:

* ``PLANTTRACER_WEB_RUNTIME=vm`` or ``PLANTTRACER_WEB_RUNTIME=lambda`` for
  runtime diagnostics and generated status output.
* A SAM/CloudFormation deployment parameter such as ``DeploymentMode`` with
  values ``vm``, ``lambda``, or ``dual``.
* ``dual`` should be the migration mode: VM, ``lambda-web``, ``lambda-resize``,
  S3, and DynamoDB all exist so traffic can be compared before cutover.

Pros
~~~~

* Keeps the existing interactive debugging path available.
* Gives an operational fallback while Lambda-web is still new.
* Lets developers run the same Flask app locally without requiring API Gateway
  or SAM local emulation for every change.

Cons
~~~~

* VM support can hide Lambda-only packaging, filesystem, timeout, and header
  bugs if tests only exercise VM mode.
* Deployment templates become more complex if they support VM-only,
  Lambda-only, and dual mode.
* Documentation and smoke tests must say which mode they validate.

Other Decisions To Make
-----------------------

Front Door And DNS
~~~~~~~~~~~~~~~~~~

Decide whether the browser sees one hostname or multiple hostnames.

One-host model:

* ``/static/*`` routes to S3.
* ``/api/*`` and HTML routes route to ``lambda-web``.
* ``/resize-api/*`` routes to ``lambda-resize``.

This is cleaner for cookies, CORS, and browser globals, but likely requires
CloudFront or careful API Gateway routing.

Multi-host model:

* HTML and metadata API use a web Lambda hostname.
* Static assets use an S3 or CloudFront hostname.
* Video APIs use the existing ``lambda-resize`` hostname.

This is simpler to phase in but needs explicit cross-origin tests.

Flask-On-Lambda Adapter
~~~~~~~~~~~~~~~~~~~~~~~

Decide how Flask runs in Lambda:

* Keep Flask and add a WSGI-to-API-Gateway adapter.
* Rewrite routes into the same AWS Lambda Powertools resolver style used by
  ``lambda-resize``.

Keeping Flask is the lower-risk migration path because it preserves existing
templates, route decorators, error handlers, and tests. A rewrite can be
considered later if Flask itself becomes the limiting factor.

Shared Code And Dependencies
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The repo already vendors selected app modules into ``lambda-resize``. A second
Lambda makes this more important.

Decide whether to:

* keep separate vendoring targets for ``lambda-resize`` and ``lambda-web``;
* create a shared installable package for code used by both;
* split dependency groups into ``web``, ``lambda-web``, ``lambda-resize``,
  ``vm``, and ``dev``.

The target should make it impossible for ``lambda-web`` to import OpenCV-only
modules accidentally.

Authentication And Cookies
~~~~~~~~~~~~~~~~~~~~~~~~~~

The current browser contract uses an ``api_key`` cookie and injects ``api_key``
into JavaScript. The migration needs explicit decisions for:

* cookie domain and path;
* ``Secure`` and ``SameSite`` attributes;
* whether S3 static assets and API calls are same-origin or cross-origin;
* whether login links keep putting ``api_key`` in the URL;
* whether public S3 pages can display login-aware navigation.

Mail And Secrets
~~~~~~~~~~~~~~~~

The web Lambda must support registration, resend-login, and course mail flows.
Decide the production mail path before cutover:

* SES through the Lambda role;
* SMTP settings loaded from Secrets Manager;
* dry-run behavior for non-production stacks.

The VM bootstrap path currently creates environment files. Lambda deployment
needs equivalent explicit parameters and secrets.

Health Checks And Diagnostics
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Current Flask startup and request handling can check DynamoDB, S3 CORS, and S3
bucket region. Decide which checks run:

* on every dynamic HTML request;
* only on an admin/config endpoint;
* as deployment smoke tests;
* as CloudWatch alarms.

Lambda health output should include the runtime mode, package version, git SHA
or build ID, table prefix, bucket name, and configured API/static bases without
exposing secrets.

Version And Build Metadata
~~~~~~~~~~~~~~~~~~~~~~~~~~

The VM can read git metadata from a checkout. A Lambda package may not have a
``.git`` directory.

Decide how to provide footer and diagnostics values such as:

* application version;
* git commit SHA;
* git branch or tag;
* build time.

Prefer explicit build-time environment variables or a generated file over
subprocess calls that assume a git checkout exists.

IAM Boundaries
~~~~~~~~~~~~~~

``lambda-web`` needs a different policy than ``lambda-resize``.

Likely web permissions:

* DynamoDB read/write/query/scan on the stack tables.
* S3 presigned POST and metadata operations for the existing movie bucket.
* SES or Secrets Manager access for mail.
* CloudWatch Logs.

Likely not needed for web:

* OpenCV/PyAV runtime dependencies.
* SQS receive/delete for tracking work.
* Long Lambda timeout.

Deployment And Rollback
~~~~~~~~~~~~~~~~~~~~~~~

Cutover should be staged:

1. Deploy ``lambda-web`` without changing production DNS.
2. Run smoke tests against its direct custom domain.
3. Run dual mode against the same DynamoDB tables and S3 bucket if safe.
4. Shift a development or demo hostname first.
5. Shift production DNS only after upload, analyze, tracing, registration,
   resend, audit, and admin flows pass.
6. Keep the VM available for rollback until the Lambda path has run through a
   real release cycle.

Local Development
~~~~~~~~~~~~~~~~~

Keep the current Makefile-first workflow. Add new targets only where they make
the mode explicit.

Possible targets:

* ``make run-local-debug`` keeps running the Flask web app locally.
* ``make run-local-lambda-debug`` keeps running ``lambda-resize`` locally.
* ``make run-local-lambda-web-debug`` runs the Lambda-web adapter locally, if
  that provides meaningful coverage beyond Flask local mode.
* ``make sam-build`` and ``make sam-deploy`` package and deploy both Lambda
  functions when deployment mode requires them.

Testing Requirements
~~~~~~~~~~~~~~~~~~~~

The migration needs tests that exercise behavior, not deployment scaffolding
alone.

Useful coverage:

* existing Flask route tests still pass in VM/local mode;
* Lambda-web handler smoke tests for ``/ping``, ``/ver``, one public page, one
  authenticated page, and one metadata API;
* MinIO-backed upload presign flow;
* DynamoDB Local-backed login, list, and metadata flows;
* browser globals are generated correctly for VM and Lambda modes;
* static asset URLs point at S3 when ``PLANTTRACER_STATIC_BASE`` is set;
* ``lambda-web`` package excludes video-processing dependencies;
* ``lambda-resize`` remains responsible for first-frame, playback URL, and
  retracing routes.

Work To Do
----------

Inventory
~~~~~~~~~

* Classify every HTML route as public static, public dynamic, authenticated
  dynamic, admin dynamic, or compatibility/debug.
* Classify every ``/api`` route by authentication requirement and downstream
  services.
* Identify VM-only assumptions: local filesystem, git subprocesses, request
  headers, proxy behavior, environment files, long-lived process caches, and
  installed system packages.
* List all static assets and decide their S3 key prefix and cache policy.

Implementation
~~~~~~~~~~~~~~

* Add a ``lambda-web`` package/handler that runs the existing Flask app behind
  HTTP API events.
* Add a Makefile target to build the web Lambda dependency set without OpenCV.
* Add a Makefile target to publish static assets to S3 or to a local equivalent
  for tests.
* Update templates so asset URLs honor ``PLANTTRACER_STATIC_BASE`` consistently.
* Add deployment-template resources for ``lambda-web``, IAM, logs, domain
  routing, and deployment mode conditions.
* Add explicit build metadata for Lambda diagnostics.
* Move VM bootstrap responsibilities into shared deployment parameters where
  they are still needed by Lambda.

Verification
~~~~~~~~~~~~

* Add local tests for Lambda-web event handling through the Makefile.
* Add deployment smoke tests for web Lambda health, a dynamic page, a metadata
  API, static asset delivery, and resize Lambda health.
* Verify registration and resend-login mail in a non-production stack.
* Verify upload and analyze in dual mode against MinIO/DynamoDB Local before
  production-like AWS testing.
* Verify rollback by leaving VM DNS and resources available during the first
  Lambda-web production cutover.

Documentation
~~~~~~~~~~~~~

* Update :doc:`ArchitectureDesign` after the target architecture is accepted.
* Update :doc:`EnvironmentVariables` for runtime mode, web Lambda URL, static
  asset base, and build metadata variables.
* Update local development docs with any new Makefile targets.
* Update deployment docs to explain ``vm``, ``lambda``, and ``dual`` modes.
* Flag user tutorial screenshots if the migration changes visible URLs,
  navigation, upload, analyze, or login behavior.

Questions For Approval
----------------------

1. Should the first Lambda-web implementation keep Flask behind a WSGI adapter,
   or should we rewrite the web/API routes into a native Lambda router?
2. Do you want one browser-visible hostname for HTML, API, static assets, and
   resize APIs, or are separate hostnames acceptable during the first cutover?
3. Which pages, if any, should become truly static S3 HTML in the first
   migration? The safest first step is static assets only.
4. Should ``DeploymentMode`` support ``vm``, ``lambda``, and ``dual`` in one
   SAM template, or should the Lambda-only deployment live in a separate
   template until it is stable?
5. Should production mail from Lambda use SES directly, SMTP credentials from
   Secrets Manager, or the same mechanism as the VM?
6. How long should the VM remain available after production DNS moves to
   Lambda-web?
