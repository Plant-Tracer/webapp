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
    routes and receives stack-scoped EventBridge work for post-upload
    normalization and tracing. It should not become the general web
    application Lambda, and it has no idle-polling event-source mapping.

The public application should use one HTTPS front door. Separate Lambda
functions do not require separate product domain names. HTTP API route
selection should be explicit:

* ``/resize-api/*`` routes to ``lambda-resize``.
* HTML pages route to ``lambda-web``.
* Flask ``/api/*`` routes route to ``lambda-web``.
* ``/static/*`` routes to ``lambda-web`` for the initial migration.

When an HTTP API uses a named stage such as ``prod``, execute-api URLs include
the stage segment, for example ``/prod/api/ver``. ``lambda-web`` normalizes that
stage prefix before handing the request to Flask so Flask routes remain
``/api/ver``, ``/static/...``, and ``/`` regardless of whether the request came
through execute-api or the custom domain.

``lambda-web`` uses AWS Lambda Powertools for Python to parse HTTP API v2
events and emit request/route diagnostics. It still uses ``apig-wsgi`` for the
actual Flask WSGI handoff because the Powertools API Gateway resolver is a
native Lambda router, not a Flask WSGI adapter.

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
  ``demo_mode``, ``user_default_course_id``, ``default_course_name``,
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
     - ``demo_tracer*.html``, ``tracer_app.html``, ``planttracer.css``,
       ``register_resend.html``, ``base.html``
     - Keep the HTML as Jinja/includes for now. Browser pages, including the
       demos, load the shared ``static/planttracer.css`` stylesheet.
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
  default course, course memberships, admin status, and demo mode;
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
``poetry run dbutil`` and ``etc/dynamodb_tables.json``.

The migration must not make stack deletion delete the long-lived S3 archive or
the DynamoDB data model.

Mail
----

The Lambda-only stack uses AWS SES for production mail. ``lambda-web`` sends
the existing MIME templates through ``ses:SendRawEmail`` when no SMTP
configuration is present. The stack sets ``SERVER_EMAIL`` and
``SERVER_EMAIL_NAME`` as stack constants and passes both to ``lambda-web``.
``SERVER_EMAIL`` is the server sender address, not a course administrator
account. That exact address must be a verified SES sender identity in the
deployment region. See :doc:`IdentityManagement`.

The ``lambda-web`` IAM role is scoped to ``ses:SendRawEmail`` for that sender
identity only, and includes a ``ses:FromAddress`` condition requiring
``SERVER_EMAIL``. If the production sender changes, update the stack constant
and verify the new address in SES before deploying.

Developers who can deploy a stack but cannot send SES mail as
the configured ``SERVER_EMAIL`` should set the SAM ``MailerDryRun`` parameter
to ``true``. The stack still deploys and registration/resend flows exercise
the mailer path, but the rendered email is written to Lambda logs instead of
being sent. Use this only for non-production stacks with test users and test
data: dry-run mail includes login links and API keys in CloudWatch logs. A
production stack must leave ``MailerDryRun`` at ``false`` and must have the SES
sender identity verified.

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

Do not replace SnapStart with a scheduled keepalive invocation. Lambda does not
guarantee that a later request reuses the periodically invoked execution
environment, especially during scaling or infrastructure recycling. A
two-minute schedule would add 21,600 invocations in a 30-day month without
providing a fast-start guarantee. SnapStart remains the explicit cold-start
control for lambda-web; SQS polling is neither a keepalive nor a cold-start
feature.

``lambda-resize`` does not use SnapStart in the initial migration. The resize
function has different runtime characteristics and should be measured before
adding SnapStart or provisioned concurrency.

Deploy Version Guard
--------------------

``make sam-build`` captures the exact ``HEAD`` SHA and stamps it into the
Lambda-web artifact. It refuses to build or deploy if a full 40-character SHA
cannot be determined; Lambda runtime code never reads ``.git`` or runs ``git``.
``/api/ver`` returns that SHA as ``git_commit`` (or ``unavailable`` for a local
Flask run).

``make sam-deploy`` and ``make sam-deploy-guided`` read the application version
from ``pyproject.toml``. Runtime code exposes the same value through
``app.constants.__version__`` for existing version-display and API callers. For
an existing stack, the deploy guard resolves the deployed application URL from
CloudFormation and fetches ``/api/ver``. If the deployed application reports the
same version as the local checkout, deploy is refused unless the operator
explicitly sets ``SAM_DEPLOY_ALLOW_SAME_VERSION=1`` for an intentional
same-version redeploy. After deployment, ``make sam-status`` compares the live
``git_commit`` with the intended local ``HEAD`` and fails if they differ.

The version bump is required because ``lambda-web`` uses SnapStart on published
Lambda versions. A normal deployment should publish a deliberately new
application version so the SnapStart snapshot and the user-visible version move
together. If deployment is blocked by the same-version guard, update
``pyproject.toml`` before deploying again.

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
5. Preserve ``lambda-resize`` asynchronous trace processing and
   ``/resize-api/*`` routes without an idle-polling event-source mapping.
6. Preserve static file serving through Flask/``lambda-web``.
7. Update deployment and smoke targets so they name the web and resize Lambda
   functions separately.
8. Run Makefile-based validation for Flask tests, Lambda handler tests, SAM
   template validation, and documentation.

Validation Requirements
-----------------------

Before PR #1113 is ready to merge, validate at least:

* existing Flask local tests still pass through ``make pytest``;
* ``lambda-web`` serves one static asset and a representative Flask route
  through API Gateway event handling, including named-stage paths such as
  ``/prod/api/ver``. Do not use root-level ``/ping`` or ``/sping`` for API
  Gateway custom-domain checks because AWS reserves those paths for service
  health checks;
* ``lambda-resize`` still serves ``/resize-api/v1/ping`` and handles
  stack-scoped EventBridge trace events;
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

``ImageBucketName`` and ``DynamoDBTablePrefix`` intentionally have no template
defaults. Every deployment must name its data resources explicitly so a new or
test stack cannot silently attach to production storage.

Because those values identify one concrete stack and its data resources, SAM
config files are local deployment state. They must not be committed to the
repository. The normal Makefile workflow is to pass ``STACK=<name>`` or its
operator-facing alias ``STACK_NAME=<name>``; the Makefile then selects
``samconfigs/<name>.toml``. The ``samconfigs/`` directory is ignored by Git,
and deployment targets also refuse to use a relative SAM config path that is
not ignored by Git.

Use one visible, ignored SAM config file per stack. For example:

.. code-block:: console

   STACK=dev-stack make sam-deploy
   STACK=alice-test make sam-deploy
   STACK_NAME=slg-dev DYNAMODB_TABLE_PREFIX=prod make sam-deploy

``STACK`` and ``STACK_NAME`` must be uppercase. GNU Make variables are
case-sensitive, so ``stack=prod`` is not the same variable and is rejected by
the SAM config guard. If both supported variables are supplied, they must
match.

Normal deployment does not rewrite the selected TOML file. The Makefile reads
it with a TOML parser, verifies that its ``stack_name`` matches the requested
target, and passes SAM's ``--stack-name`` option explicitly. If
``DYNAMODB_TABLE_PREFIX`` is also supplied, the Makefile verifies it against
the config's ``DynamoDBTablePrefix`` override (ignoring one conventional
trailing hyphen) and refuses a mismatch. Other deployment parameters continue
to come from the per-stack TOML file.

``sam deploy --guided`` can also create the selected stack config:

.. code-block:: console

   STACK=alice-test make sam-deploy-guided

If ``samconfigs/alice-test.toml`` does not exist yet, the Makefile creates a
minimal ignored config file before invoking SAM because the SAM CLI requires
the ``--config-file`` path to be readable even in guided mode. A Python TOML
writer creates or updates this bootstrap file so TOML quoting and existing
values are preserved. When a stack selector is set, the bootstrap config
includes ``stack_name`` so the normal deploy-version guard can still run before
the guided deployment.

For a stack named ``app``, the selected config is ``samconfigs/app.toml`` and
the template creates ``https://app.planttracer.com/`` when ``BaseDomain`` is
``planttracer.com``. The hostname comes from ``AWS::StackName`` and
``BaseDomain`` in ``template.yaml``. The Makefile passes ``--stack-name app``
during both normal and guided deploys and refuses an existing
``samconfigs/app.toml`` whose ``stack_name`` is not ``app``.

The Makefile still accepts ``SAM_CONFIG=<path>`` as an explicit escape hatch.
For compatibility with older local setups, omitting ``STACK`` and ``SAM_CONFIG``
uses ``samconfig.toml``. Any relative config path must be ignored by Git.

SAM supports multiple profiles in a single config file, but this project avoids
that pattern. With multiple stacks in flight, separate visible files selected by
``STACK`` or ``STACK_NAME`` make the target stack obvious and work better with
SAM's habit of rewriting config during guided deploys.

Cutover Runbook
---------------

Validate each stack on its own hostname, for example
``https://{stack}.planttracer.com/``. This migration does not depend on moving
a shared production DNS record to Lambda; new and test deployments come up as
separate named stacks. SAM config files are stack-local deployment state and
are not committed to the repository. Use ``STACK=<name>`` or
``STACK_NAME=<name>`` to select the ignored ``samconfigs/<name>.toml`` config
for the stack being tested. The branch must be pushed before ``make sam-build``
will build artifacts. This prevents deploying local-only commits that nobody
else can inspect or rebuild.

Preflight:

* confirm ``git status`` is clean and the branch has no unpushed commits;
* confirm ``pyproject.toml`` has the intended version;
* confirm ``STACK`` or ``STACK_NAME`` names the intended stack and the selected
  ``samconfigs/<stack>.toml`` has the intended table prefix;
* confirm the S3 movie bucket and DynamoDB table prefix are the intended test
  resources;
* if the stack operator cannot send SES mail as the configured ``SERVER_EMAIL``,
  confirm the SAM config sets ``MailerDryRun="true"`` and uses only test users;
* run ``make check``;
* run ``make template-lint``;
* run ``make sam-build``.

Deploy:

* run ``STACK=<name> make sam-deploy`` for an existing configured stack, or
  ``STACK=<name> make sam-deploy-guided`` for a new stack. ``STACK_NAME`` is an
  equivalent alias;
* let ``make sam-status`` verify ``/api/ver`` and its ``git_commit``,
  ``/static/planttracer.js``, and ``/resize-api/v1/ping``. The deploy targets
  stamp the built ``lambda-resize`` artifact before ``sam deploy``. The web
  version API response is printed in full, and resize ping should report the
  application version and UTC deployment timestamp;
* let the deploy target run ``make sam-deployed-workflow-test``. It creates or
  reuses a stack-specific test course/user, uploads the circumnutation fixture
  through ``uploads/{stack}/``, verifies the movie appears in the deployed
  movie list, waits for EventBridge/post-upload processing, and downloads the
  original movie. It traces all frames from committed reference starting
  markers, verifies the initial and final Apex positions within two pixels,
  validates CSV and XLSX exports, and compares the downloaded traced movie's
  final frame to its committed rendering reference. It then removes its movie
  artifacts;
* inspect recent logs with ``make sam-logs-web`` and ``make sam-logs-resize``
  if any smoke check reports a failure.

Course initialization is a separate post-deploy data step. It replaces VM
``etc/bootstrap.sh`` section 10 and must not run from Lambda cold start or from
CloudFormation resource creation. After the stack is deployed and the intended
``DynamoDBTablePrefix`` is confirmed, create or verify the non-demo course with
``make sam-course-create``:

.. code-block:: console

   AWS_REGION=us-east-1 SAM_CONFIG=<path> \
     COURSE_CREATE_FLAGS="--course_id BIO101 --course_name 'Plant Biology 101' --admin_email teacher@example.edu --admin_name 'Teacher Name'" \
     make sam-course-create

The target reads the table prefix, application URL, and ``MailerDryRun`` value
from the selected stack, then delegates to ``poetry run dbutil create-course
--send-email``. Rerunning it is safe when the course already exists with the
same name: it verifies the course administrator relationship and sends the
course setup/login email again. If the existing course id has a different
name, the command fails so operators do not silently reuse the wrong course.
For dry-run stacks, the email is rendered to logs through ``MAILER_DRY_RUN``;
for production, verify SES sender access before running it.

Manual smoke checks on the non-production stack:

* open ``https://{stack}.planttracer.com/`` and verify the home page and static
  assets load;
* verify ``/api/ver`` returns ``__version__``, a 40-character ``git_commit``,
  ``sys_version``, and ``stack_name``; compare ``git_commit`` with the source
  commit selected for deployment;
* verify ``/resize-api/v1/ping`` returns ``{"status": "ok"}``,
  ``app_version``, ``deployed_at``, and ``stack_parameters``;
* register a test user and confirm the registration email path works;
* resend a login link and confirm the user can log in;
* for ``MailerDryRun=true`` stacks, confirm the login email appears in Lambda
  web logs and treat the logged link as test-only secret material;
* confirm the automated deployed workflow uploaded a small movie through the
  stack's EventBridge rule and completed its short trace;
* open the analysis page, load the first frame, save at least one marker
  change, and start tracing;
* confirm the trace job reaches ``lambda-resize`` through EventBridge and
  produces expected artifacts or a clear user-visible status;
* verify audit/admin pages still render for an admin user.

Do not treat a new stack hostname as ready for users until it passes the smoke
matrix and the mail/secrets path for that stack is confirmed. Keep the previous
known-good stack hostname available until the new stack has been accepted.

Rollback:

* if a new stack fails validation, keep users on the previous known-good stack
  hostname;
* if an existing stack was updated in place, redeploy the previous known-good
  version or rebuild the stack under a new hostname for comparison;
* if login, registration, upload, or tracing fails after users begin testing a
  stack, stop directing testers to that hostname, then inspect CloudWatch logs
  and stack events;
* do not delete the movie S3 bucket or DynamoDB tables during rollback;
* preserve the failed stack until logs, CloudFormation events, and Lambda
  versions have been captured for diagnosis.
