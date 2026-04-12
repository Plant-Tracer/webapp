Local Development and GitHub Actions
====================================

This document describes the local testing model for PlantTracer after the move
to ``lambda-resize``.

The short version is:

* Flask remains the local HTML and metadata server.
* A second local process runs the Lambda HTTP API.
* DynamoDB Local and MinIO remain the local data stores.
* Local retracing is asynchronous, but it does **not** require a real SQS
  service.

This document is Mac-first. That is the supported local developer workflow for
now.


Why This Document Exists
------------------------

The old local workflow assumed that ``make run-local-debug`` was enough by
itself. That was true when the VM handled first-frame extraction and tracking.
It is no longer true now that:

* HTML is served by Flask,
* metadata writes are served by Flask API, and
* frame extraction and tracing live in ``lambda-resize``.

As a result, local retracing is currently broken unless a second local Lambda
endpoint is also running.


Architecture Summary
--------------------

PlantTracer now has a split runtime:

* **Flask app** serves HTML and the metadata API.
* **Lambda API** serves frame and tracing operations.
* **DynamoDB Local** stores metadata and trackpoints.
* **MinIO** stores uploaded movies, traced movies, and frame ZIP files.

This matches the design rules in :doc:`ArchitectureDesign`:

* frames and video processing live in Lambda,
* HTML lives in Flask,
* metadata lives in Flask API.


Local Topology
--------------

The recommended local process layout on macOS is:

+----------------------+---------------------------+-------------------------------------------+
| Process              | Default endpoint          | Responsibility                            |
+======================+===========================+===========================================+
| Flask dev server     | ``http://127.0.0.1:8080`` | HTML pages and Flask API                  |
+----------------------+---------------------------+-------------------------------------------+
| Local Lambda server  | ``http://127.0.0.1:9811`` | ``/resize-api/v1/*`` endpoints and async  |
|                      |                           | retracing worker                          |
+----------------------+---------------------------+-------------------------------------------+
| DynamoDB Local       | ``http://127.0.0.1:8000`` | Local metadata store                      |
+----------------------+---------------------------+-------------------------------------------+
| MinIO                | ``http://127.0.0.1:9000`` | Local S3-compatible object store          |
+----------------------+---------------------------+-------------------------------------------+

Port ``9811`` is suggested for the local Lambda server because MinIO already
uses ``9000`` for its API and ``9001`` for its console.


Local Testing Goals
-------------------

The local workflow must let a developer:

* run the browser UI against local Flask,
* upload a movie into local MinIO,
* fetch first frames through the local Lambda endpoint,
* save marker edits through Flask,
* retrace from the current frame,
* watch Lambda debug output in a separate Terminal or iTerm2 window,
* use the same DynamoDB Local and MinIO state from both processes.


Design Decision: Use a Second Native Python Process
---------------------------------------------------

The recommended approach is a dedicated local Lambda debug server, started in a
second Terminal window.

That server should:

* expose the same HTTP routes as deployed Lambda, currently
  ``/resize-api/v1/ping``, ``/resize-api/v1/first-frame``, and
  ``/resize-api/v1/trace-movie``,
* translate incoming local HTTP requests into API Gateway v2 style events,
* call the real ``resize_app.main.lambda_handler()``,
* print all stdout, stderr, and logger output in that Terminal window,
* run a local async worker for retrace jobs.

The goal is to keep local behavior as close as possible to deployed Lambda while
still being easy to run and easy to debug on a Mac.


Design Decision: Do Not Require a Real Local SQS Service
--------------------------------------------------------

For local development we do **not** need a full SQS emulator shared across
processes.

Production uses SQS so the HTTP trace request can return quickly while the
tracking job continues in the background. Locally, we can preserve that
behavior more simply:

* the local Lambda HTTP process accepts ``POST /resize-api/v1/trace-movie``,
* it queues the work into an in-process local queue,
* a background worker thread in that same process drains the queue and runs the
  tracing pipeline,
* the browser continues polling Flask metadata exactly as it does in
  production.

This gives us the important behavior:

* HTTP request returns immediately,
* tracing is asynchronous,
* all tracing logs are visible in one dedicated window,
* no extra queue service needs to be installed or orchestrated.

If we later want higher-fidelity AWS emulation, we can add a SAM or Finch mode
separately. It is not required for the primary Mac workflow.


Environment Variables
---------------------

The Flask and local Lambda processes should share the same local storage
configuration:

* ``AWS_REGION=local``
* ``AWS_ACCESS_KEY_ID=minioadmin``
* ``AWS_SECRET_ACCESS_KEY=minioadmin``
* ``AWS_ENDPOINT_URL_DYNAMODB=http://127.0.0.1:8000/``
* ``AWS_ENDPOINT_URL_S3=http://127.0.0.1:9000/``
* ``PLANTTRACER_S3_BUCKET=planttracer-local``
* ``DYNAMODB_TABLE_PREFIX=demo-`` or another local prefix
* ``LOG_LEVEL=DEBUG`` during interactive debugging

In addition, Flask supports an explicit local Lambda override:

* ``PLANTTRACER_LAMBDA_API_BASE=http://127.0.0.1:9811/``

Flask prefers this explicit variable over deriving the Lambda hostname
from ``HOSTNAME`` and ``DOMAIN``. The hostname-based rule is correct for
deployed stacks, but it is not sufficient for local development.

These are **process environment variables**. They are visible to Flask and the
local Lambda server, but they are **not** automatically visible to JavaScript in
the browser.

For browser-side JavaScript to see any of this information, Flask must:

* read the process environment,
* place selected values into the template dictionary returned by
  ``page_dict()``,
* render those values into HTML,
* let the browser execute the resulting inline JavaScript.


JavaScript Runtime Variables
----------------------------

When this document says that a value is "injected by Flask", it means the
following pipeline:

1. A route in ``flask_app.py`` calls ``render_template(..., **page_dict(...))``.
2. ``page_dict()`` in ``src/app/apikey.py`` builds a Python dictionary named
   ``ret``.
3. ``base.html`` reads selected dictionary entries through Jinja template
   substitution.
4. ``base.html`` emits an inline ``<script>`` block that creates browser-global
   JavaScript constants.
5. Frontend JavaScript reads those constants during normal runtime.

In other words, the data path is:

``Flask environment/config -> page_dict() -> Jinja template variables -> inline JavaScript constants -> browser runtime``

The base template currently emits these globals:

.. code-block:: html

   <script>
     const API_BASE = "{{API_BASE}}";
     const LAMBDA_API_BASE = "{{ lambda_api_base }}";
     const api_key = "{{api_key}}";
     const user_id = "{{user_id}}";
     const demo_mode = true_or_false;
     const user_primary_course_id = "{{user_primary_course_id}}";
     const MAX_FILE_UPLOAD = {{MAX_FILE_UPLOAD}};
     const admin = true_or_false;
   </script>

Although ``planttracer.js`` is loaded earlier in ``base.html`` using
``type="module"``, module scripts are deferred by the browser until HTML parsing
finishes. That means the inline constants above are in place before the module
code runs.

Only the globals that matter to the browser runtime are discussed below.


Relevant Browser Globals
^^^^^^^^^^^^^^^^^^^^^^^^

+--------------------------+--------------------------------+-----------------------------------------------+--------------------------------------------------------+
| JavaScript constant      | Dictionary key from Flask      | Where Flask gets it                            | How the browser uses it                                |
+==========================+================================+===============================================+========================================================+
| ``API_BASE``             | ``C.API_BASE`` / ``API_BASE``  | ``PLANTTRACER_API_BASE`` env var, else ``''`` | Prefix for Flask API calls such as register, resend,   |
|                          |                                |                                               | list movies, get metadata, save trackpoints, and       |
|                          |                                |                                               | rotate movie.                                          |
+--------------------------+--------------------------------+-----------------------------------------------+--------------------------------------------------------+
| ``LAMBDA_API_BASE``      | ``lambda_api_base``            | Currently ``get_lambda_api_base()`` in        | Prefix for Lambda HTTP API calls such as               |
|                          |                                | ``apikey.py``. In deployed stacks this is     | ``/resize-api/v1/ping``, first-frame fetch,            |
|                          |                                | derived from ``HOSTNAME`` and ``DOMAIN``. For | retrace requests, and playback URLs served by          |
|                          |                                | local debugging the intended source is an     | Lambda.                                                |
|                          |                                | explicit override such as                     |                                                        |
|                          |                                | ``PLANTTRACER_LAMBDA_API_BASE``.              |                                                        |
+--------------------------+--------------------------------+-----------------------------------------------+--------------------------------------------------------+
| ``api_key``              | ``api_key``                    | ``get_user_api_key()`` using URL parameter or | Authorization token sent by frontend code to both      |
|                          |                                | cookie, then validated through the current    | Flask and Lambda APIs. Without this, most logged-in    |
|                          |                                | user session.                                 | operations fail.                                       |
+--------------------------+--------------------------------+-----------------------------------------------+--------------------------------------------------------+
| ``user_id``              | ``user_id``                    | The validated user record for the current     | Lets the frontend identify which movies belong to the  |
|                          |                                | ``api_key``.                                  | current user and which controls should be shown.       |
+--------------------------+--------------------------------+-----------------------------------------------+--------------------------------------------------------+
| ``demo_mode``            | ``demo_mode``                  | ``in_demo_mode()`` in ``apikey.py``.          | Disables mutating actions in the browser, changes      |
|                          |                                | Enabled when ``DEMO_MODE`` is set or the      | status text, and hides controls that should not be     |
|                          |                                | request hostname has a ``-demo`` label.       | available in demo mode.                                |
+--------------------------+--------------------------------+-----------------------------------------------+--------------------------------------------------------+
| ``user_primary_course_id`` | ``user_primary_course_id``   | The current user's validated record.          | Used by course-scoped browser features such as user    |
|                          |                                |                                               | management and course movie filtering.                 |
+--------------------------+--------------------------------+-----------------------------------------------+--------------------------------------------------------+
| ``admin``                | ``admin``                      | ``odb.check_course_admin(...)`` for the       | Enables admin-only browser behavior such as bulk       |
|                          |                                | current user, except in demo mode.            | registration and broader movie-management controls.    |
+--------------------------+--------------------------------+-----------------------------------------------+--------------------------------------------------------+
| ``MAX_FILE_UPLOAD``      | ``MAX_FILE_UPLOAD``            | Constant from ``app.constants.C``.            | Client-side upload size check before the browser       |
|                          |                                |                                               | attempts the S3 upload.                                |
+--------------------------+--------------------------------+-----------------------------------------------+--------------------------------------------------------+


Where Each Variable Is Used
^^^^^^^^^^^^^^^^^^^^^^^^^^^

The most important runtime uses are:

* ``API_BASE``

  * Used throughout ``src/app/static/planttracer.js`` for Flask endpoints such
    as ``api/new-movie``, ``api/get-movie-metadata``, ``api/rotate-movie``,
    ``api/list-movies``, and ``api/set-metadata``.
  * Used in ``src/app/static/canvas_tracer_controller.js`` for
    ``api/put-frame-trackpoints`` and ``api/get-movie-metadata``.
  * Used in ``src/app/static/audit.js`` and ``src/app/static/users.js`` for
    audit and user-management calls.

* ``LAMBDA_API_BASE``

  * Used in ``src/app/static/planttracer.js`` for Lambda health checks and
    first-frame URL construction.
  * Used in ``src/app/static/canvas_tracer_controller.js`` for
    ``/resize-api/v1/trace-movie`` and for initial frame loading on the Analyze
    page.
  * This is the variable that must point at the local Lambda debug process when
    we are debugging retracing on a Mac.

* ``api_key``

  * Sent on almost every authenticated request from the browser.
  * Included in Flask form posts and in Lambda calls such as retrace and
    first-frame fetch.

* ``user_id``, ``demo_mode``, ``user_primary_course_id``, ``admin``

  * Used by the browser to decide which controls to show, which actions are
    allowed, and which movies belong in each UI section.

* ``MAX_FILE_UPLOAD``

  * Used by the upload UI to reject oversized files before upload begins.

Two values defined in ``base.html`` are intentionally not discussed further
here:

* ``STATIC_BASE`` is currently defined but not meaningfully used by the runtime
  JavaScript in this repo.
* ``version`` is useful for display/debugging in rendered pages, but not for
  the operational browser logic discussed in this document.


Recommended Make Targets
------------------------

The intended local commands are:

.. code-block:: bash

   make start_local_dynamodb
   make start_local_minio
   make make-local-bucket
   make make-local-demo

   # Terminal window 1: local Lambda logs
   make run-local-lambda-debug

   # Terminal window 2: Flask UI + Flask API
   make run-local-debug

``run-local-debug`` is the main developer entry point for the Flask side of the
local workflow. Its job is to:

* ensure demo mode is **off** for this Flask process,
* print a login link for the local admin user,
* export ``PLANTTRACER_LAMBDA_API_BASE=http://127.0.0.1:9811/``,
* start Flask on ``localhost:8080``,
* on macOS, try to open a second Terminal or iTerm2 window running
  ``make run-local-lambda-debug``.

``run-local-demo-debug``:

* seeds the local demo dataset if needed,
* ensures demo mode is **on** for this Flask process,
* sets ``DEMO_MODE=1`` and ``DEMO_COURSE_ID=demo-course``,
* starts Flask on ``localhost:8080`` without requiring a login link.

``run-local-lambda-debug``:

* vendor Lambda-shared app code if needed,
* set the same local AWS and table-prefix environment variables,
* start the local Lambda HTTP bridge on ``localhost:9811``,
* start the in-process local retrace worker,
* log every request and every tracing step to stdout/stderr.


Browser Request Flow
--------------------

With the two-process local model, the browser behaves like this:

1. Load HTML from Flask at ``http://127.0.0.1:8080``.
2. Read the browser globals emitted by ``base.html``.

   * ``API_BASE`` should point at Flask.
   * ``LAMBDA_API_BASE`` should point to ``http://127.0.0.1:9811/`` in local
     mode.
   * ``api_key`` should contain the current login token.

3. Request first frame from the local Lambda endpoint.
4. Save marker edits through Flask ``/api/put-frame-trackpoints``.
5. Request retrace through local Lambda ``/resize-api/v1/trace-movie``.
6. Poll Flask ``/api/get-movie-metadata`` until tracing completes.
7. Fetch the generated ZIP or traced movie from MinIO through signed URLs.

This keeps the browser contract aligned with production:

* Flask owns HTML and metadata APIs.
* Lambda owns frame and tracing APIs.


Local Retrace Flow
------------------

When the user retraces from frame ``N`` locally:

1. The browser sends ``movie_id`` and ``frame_start=N`` to the local Lambda
   endpoint.
2. The local Lambda HTTP handler validates the request and enqueues a local
   retrace job.
3. The local worker removes stored trackpoints for frames ``N+1..end``.
4. The worker resumes tracing at frame ``N+1``.
5. Trackpoints are written back to DynamoDB Local.
6. The traced MP4 and frame ZIP are written to MinIO.
7. Flask metadata polling sees the updated movie status and URLs.

This is the same retrace semantics described in
``instructions-for-llms/planttracer-storage.md``.


Why Not Make Flask Pretend To Be Lambda
---------------------------------------

It is tempting to add Lambda routes directly to Flask for local use. We do not
want to do that.

Keeping Lambda in its own local process has several advantages:

* it preserves the deployment boundary,
* it keeps Lambda-only imports and dependencies out of the Flask runtime path,
* it gives us a dedicated debugging window for retrace logs,
* it reduces the chance that local-only shortcuts hide production bugs.


Why Native Python First Instead of SAM Local
--------------------------------------------

AWS SAM local emulation may still be useful later, especially for deployment
parity. It is not the preferred primary workflow for day-to-day Mac debugging.

Native Python is better for the first local retrace workflow because:

* it starts faster,
* it is easier to debug interactively,
* stdout and stderr are simpler to watch,
* the current problem is architectural split, not container fidelity,
* SQS behavior is easier to model with an in-process queue than with a second
  emulator.

If we later add a containerized mode using Finch, it should be an additional
option, not the only local testing path.


GitHub Actions
--------------

GitHub Actions should continue to use local infrastructure only:

* DynamoDB Local,
* MinIO,
* direct Python tests,
* JavaScript tests,
* Lambda handler unit and integration tests.

GitHub Actions does **not** need the macOS two-window workflow. CI should focus
on:

* Flask tests against local services,
* Lambda unit tests that call ``lambda_handler`` directly,
* end-to-end local tracing tests that run the tracing pipeline against MinIO and
  DynamoDB Local,
* browser tests only where they provide unique value.


Planned Verification
--------------------

Once the local Lambda server is implemented, local testing should cover at least
these cases:

* ``GET /resize-api/v1/ping`` returns ``status=ok``.
* ``GET /resize-api/v1/first-frame`` returns a JPEG for a movie in MinIO.
* ``POST /resize-api/v1/trace-movie`` returns quickly and starts background
  tracing.
* Flask ``/api/get-movie-metadata`` eventually reports tracing completion.
* A browser-driven local retrace updates later frames after the user edits frame
  ``N``.


Current Status
--------------

At the time this document was last updated:

* the split Flask/Lambda architecture is the active design,
* ``run-local-debug`` starts the Flask side of the local workflow and ensures a
  local Lambda endpoint is available,
* the repo includes a dedicated ``run-local-lambda-debug`` workflow, and
* the two-process Mac local testing model described above is the supported
  local retracing workflow.
