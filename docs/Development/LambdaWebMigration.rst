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

Static HTML Shell Decision
--------------------------

The initial Lambda-only migration keeps Jinja-rendered HTML pages in
``lambda-web``. Moving pages to static HTML shells should be a later,
incremental project after cookie/API cleanup and versioned static assets are
designed.

This decision is conservative because the current templates are not just static
markup. Routes call ``render_template(..., **page_dict(...))`` and
``page_dict()`` performs authentication lookup, course/admin lookup, demo-mode
selection, runtime URL selection, and JavaScript bootstrap injection. The base
template uses that state for:

* browser globals: ``API_BASE``, ``LAMBDA_API_BASE``, ``api_key``, ``user_id``,
  ``demo_mode``, ``user_primary_course_id``, ``primary_course_name``,
  ``MAX_FILE_UPLOAD``, ``MOVIE_STATE``, and ``admin``;
* authenticated navigation and logged-in user/course display;
* admin-only and demo-mode menu behavior;
* version and git build display.

Current template classification:

.. list-table::
   :header-rows: 1

   * - Template group
     - Examples
     - Static-shell status
   * - Public informational pages
     - ``about.html``, ``privacy.html``, ``tos.html``, ``error.html``
     - Good later candidates, but today they still inherit dynamic navigation
       and version display from ``base.html``.
   * - Public account pages
     - ``index.html``, ``login.html``, ``register.html``, ``logout.html``,
       ``welcome.html``
     - Possible later candidates after login links are consumed server-side,
       auth cookies are canonical, and the browser has a session endpoint.
   * - Authenticated app pages
     - ``list.html``, ``upload.html``, ``analyze.html``, ``users.html``,
       ``audit.html``, ``processing.html``
     - Not initial candidates. They rely on injected user, course, admin, demo,
       max-upload, and API-key state.
   * - Demo/tracer pages and shared includes
     - ``demo_tracer*.html``, ``tracer_app.html``, ``tracer_app.css``,
       ``register_resend.html``, ``base.html``
     - Keep as Jinja/includes for now. A later migration should treat shared
       includes as normal static assets only after an asset versioning plan.
   * - Operational and email templates
     - ``config_error.html``, ``debug.html``, ``version.txt``,
       ``email_login.html``, ``email_course_created.html``
     - Keep server-rendered. These are diagnostics or MIME templates, not
       browser static-shell targets.

A future static-shell migration must define replacement browser contracts
before changing templates:

* a public runtime config endpoint or static config artifact for
  ``API_BASE``, ``LAMBDA_API_BASE``, ``MOVIE_STATE``, ``MAX_FILE_UPLOAD``,
  app version, and asset version;
* a same-origin ``/api/session`` endpoint for logged-in state, user identity,
  primary course, admin status, and demo mode;
* a login-link flow that consumes ``?api_key=...``, sets the cookie, and
  redirects to a clean URL before browser JavaScript runs;
* a CSRF/log-safety decision for cookie-authenticated mutating endpoints;
* a versioned static asset manifest before moving HTML, JavaScript, or CSS to
  long-lived external caching.

Any later implementation should update ``docs/Development/FlaskAPI.md``,
``docs/Development/ClientLambdaAPI.md``,
``docs/Development/EnvironmentVariables.rst``, and local-development docs.
Tests should cover the new config/session contracts, login-link cleanup,
authenticated and anonymous navigation states, admin/demo behavior, and the
existing Selenium upload/list/analyze flows.

Data Ownership
--------------

DynamoDB tables are external to CloudFormation ownership. The stack receives
the table prefix and grants prefix-scoped permissions, but table creation and
schema maintenance remain handled by repository tooling such as
``src/dbutil.py`` and ``etc/dynamodb_tables.json``.

The migration must not make stack deletion delete the long-lived S3 archive or
the DynamoDB data model.

Mail
----

The Lambda-only stack uses AWS SES for production mail. ``lambda-web`` sends
the existing MIME templates through ``ses:SendRawEmail`` when no SMTP
configuration is present. The stack sets ``SERVER_EMAIL`` to the stack constant
``admin@planttracer.com``. That exact address must be a verified SES sender
identity in the deployment region.

The ``lambda-web`` IAM role is scoped to ``ses:SendRawEmail`` for that sender
identity only, and includes a ``ses:FromAddress`` condition requiring
``admin@planttracer.com``. If the production sender changes, update the stack
constant and verify the new address in SES before deploying.

Developers who can deploy a stack but cannot send SES mail as
``admin@planttracer.com`` should set the SAM ``MailerDryRun`` parameter to
``true``. The stack still deploys and registration/resend flows exercise the
mailer path, but the rendered email is written to Lambda logs instead of being
sent. Use this only for non-production stacks with test users and test data:
dry-run mail includes login links and API keys in CloudWatch logs. A production
stack must leave ``MailerDryRun`` at ``false`` and must have the SES sender
identity verified.

Do not put SMTP credentials in ``samconfig.toml`` or committed environment
files. Local development continues to use Mailpit through ``SMTPCONFIG_JSON``.
The application mailer still supports ``PLANTTRACER_CREDENTIALS``,
``SMTPCONFIG_JSON``, and ``SMTPCONFIG_ARN`` for explicit SMTP configurations,
but the Lambda-only stack does not set ``SMTPCONFIG_ARN`` and does not grant
Secrets Manager access by default. If SMTP-backed Lambda mail is needed later,
add a dedicated SAM parameter for the secret ARN and scope
``secretsmanager:GetSecretValue`` to that one secret.

Cold Starts
-----------

``lambda-web`` enables Lambda SnapStart on the published ``live`` alias. This
reduces cold-start initialization cost for the Flask web runtime, but it does
not keep an execution environment continuously warm. Any code that relies on
unique values, credentials, timestamps, temporary data, or network connections
from module initialization must tolerate Lambda restore behavior.

``lambda-resize`` does not use SnapStart in the initial migration. The resize
function has different runtime characteristics and should be measured before
adding SnapStart or provisioned concurrency.

Deploy Version Guard
--------------------

``make sam-deploy`` and ``make sam-deploy-guided`` require
``src/app/constants.py`` and ``pyproject.toml`` to contain the same application
version. For an existing stack, the deploy guard resolves the deployed
application URL from CloudFormation and fetches ``/api/ver``. If the deployed
application reports the same version as the local checkout, deploy is refused
unless the operator explicitly sets ``SAM_DEPLOY_ALLOW_SAME_VERSION=1`` for an
intentional same-version redeploy.

The version bump is required because ``lambda-web`` uses SnapStart on published
Lambda versions. A normal deployment should publish a deliberately new
application version so the SnapStart snapshot and the user-visible version move
together. If deployment is blocked by the same-version guard, update both
``src/app/constants.py`` and ``pyproject.toml`` before deploying again.

The deployed-version check is recovery tolerant. If the stack does not exist,
CloudFormation outputs are missing, DNS is not usable, or ``/api/ver`` cannot
return valid JSON, the guard prints a warning and allows the deploy. This keeps
first deploys and repair deploys from being blocked by a broken stack.

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

SAM Config Files
----------------

SAM stores deployment choices in a TOML config file. That file is not the
application template; ``template.yaml`` is still the source-controlled
CloudFormation/SAM definition. The SAM config records the local operator's
selected deployment target and deploy-time parameters, including values such
as:

* ``stack_name``;
* AWS region;
* artifact bucket or ``resolve_s3`` behavior;
* CloudFormation capabilities;
* ``parameter_overrides`` for ``HostedZoneId``, ``BaseDomain``,
  ``WildcardCertificateArn``, ``ImageBucketName``, ``LogLevel``,
  ``MailerDryRun``, and ``DynamoDBTablePrefix``.

Because those values identify one concrete stack and its data resources, SAM
config files are local deployment state. They must not be committed to the
repository. The Makefile defaults to ``SAM_CONFIG=samconfig.toml`` for
compatibility with the SAM CLI, but ``.gitignore`` ignores ``samconfig*.toml``,
``.samconfig*.toml``, and ``samconfig.toml-*``. Deployment targets also refuse
to use a SAM config file that is tracked by Git.

Use one ignored SAM config file per stack. For example:

.. code-block:: console

   AWS_REGION=us-east-1 SAM_CONFIG=.samconfig.dev-stack.toml make sam-deploy
   AWS_REGION=us-east-1 SAM_CONFIG=.samconfig.alice-test.toml make sam-deploy
   AWS_REGION=us-east-1 SAM_CONFIG=.samconfig.prod.toml make sam-deploy

``sam deploy --guided`` can also create the selected file:

.. code-block:: console

   AWS_REGION=us-east-1 SAM_CONFIG=.samconfig.alice-test.toml make sam-deploy-guided

SAM supports multiple profiles in a single config file, but this project should
avoid that pattern. With multiple stacks in flight, separate files make the
target stack visible in the command line and avoid accidentally using a stale
default profile from a shared TOML file. Separate files also work better with
SAM's habit of rewriting config during guided deploys.

Cutover Runbook
---------------

Validate a non-production stack before any production DNS change. SAM config
files are stack-local deployment state and are not committed to the repository.
Use ``SAM_CONFIG=<path>`` to select the ignored config for the stack being
tested. The branch must be pushed before ``make sam-build`` will build
artifacts. This prevents deploying local-only commits that nobody else can
inspect or rebuild.

Preflight:

* confirm ``git status`` is clean and the branch has no unpushed commits;
* confirm ``src/app/constants.py`` and ``pyproject.toml`` have the same version;
* confirm ``SAM_CONFIG`` points to an untracked local SAM config for the
  intended non-production stack and table prefix;
* confirm the S3 movie bucket and DynamoDB table prefix are the intended test
  resources;
* if the stack operator cannot send SES mail as ``admin@planttracer.com``,
  confirm the SAM config sets ``MailerDryRun="true"`` and uses only test users;
* run ``make check``;
* run ``make template-lint``;
* run ``make sam-build``.

Deploy:

* run ``AWS_REGION=us-east-1 SAM_CONFIG=<path> make sam-deploy`` for an
  existing configured stack, or
  ``AWS_REGION=us-east-1 SAM_CONFIG=<path> make sam-deploy-guided`` for a new
  stack;
* let ``make sam-status`` verify ``/ping``, ``/static/planttracer.js``, and
  ``/resize-api/v1/ping``;
* inspect recent logs with ``make sam-logs-web`` and ``make sam-logs-resize``
  if any smoke check reports a failure.

Manual smoke checks on the non-production stack:

* open ``https://{stack}.planttracer.com/`` and verify the home page and static
  assets load;
* verify ``/ping`` returns ``{"status": "ok"}``;
* verify ``/resize-api/v1/ping`` returns ``{"status": "ok"}``;
* register a test user and confirm the registration email path works;
* resend a login link and confirm the user can log in;
* for ``MailerDryRun=true`` stacks, confirm the login email appears in Lambda
  web logs and treat the logged link as test-only secret material;
* upload a small movie and confirm it appears in the list page;
* open the analysis page, load the first frame, save at least one marker
  change, and start tracing;
* confirm the trace job reaches SQS/``lambda-resize`` and produces expected
  artifacts or a clear user-visible status;
* verify audit/admin pages still render for an admin user.

Production DNS cutover must wait until the non-production stack passes the
smoke matrix and the production mail/secrets path is confirmed. Record the
pre-cutover DNS target and TTL before changing any record.

Rollback:

* if only DNS was changed, restore the previous Route53 record target and TTL;
* if the Lambda stack was updated but DNS was not moved, redeploy the previous
  known-good version or leave traffic on the existing production target;
* if login, registration, upload, or tracing fails after DNS cutover, restore
  the previous DNS target first, then inspect CloudWatch logs and stack events;
* do not delete the movie S3 bucket or DynamoDB tables during rollback;
* preserve the failed stack until logs, CloudFormation events, and Lambda
  versions have been captured for diagnosis.
