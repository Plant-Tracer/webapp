Demo Mode
=========

Demo mode is a runtime behavior of the web application. It is distinct from the
existence of demo data in DynamoDB and S3.

There are two separate concepts:

* ``DEMO_MODE`` controls whether the webapp is running in demo mode.
* ``DEMO_COURSE_ID`` identifies which course contains the demo dataset.

The important rule is:

* ``DEMO_COURSE_ID`` by itself does **not** enable demo mode.


How Demo Mode Is Enabled
------------------------

PlantTracer runs in demo mode when either of these conditions is true:

* the process environment contains ``DEMO_MODE``
* the incoming request host has a hostname label ending in ``-demo``

Examples:

* ``DEMO_MODE=1`` in the process environment enables demo mode
* ``simsong-demo.planttracer.com`` enables demo mode because the hostname
  contains a ``-demo`` label
* ``simsong.planttracer.com`` is **not** demo mode unless ``DEMO_MODE`` is set

This allows a deployment such as:

* ``simsong.planttracer.com`` for normal mode
* ``simsong-demo.planttracer.com`` for demo mode

with both names pointing at the same VM.


What ``DEMO_COURSE_ID`` Means
-----------------------------

``DEMO_COURSE_ID`` identifies the course that contains the demo data. In local
development the Makefile seeds ``demo-course``.

Today the runtime switch for demo behavior is ``DEMO_MODE`` or the ``-demo``
hostname rule. ``DEMO_COURSE_ID`` is still useful because it names the demo
course dataset used by local setup and deployment conventions.


Behavior in Demo Mode
---------------------

When the app is in demo mode:

* anonymous users are treated as the demo user
* ``get_user_api_key()`` returns the fixed demo API key
* the UI hides mutating actions such as upload and many editing controls
* Flask passes ``demo_mode=True`` into Jinja templates
* the browser receives the global JavaScript constant ``demo_mode = true``

In other words, demo mode is not just "logged in as the demo user." It is a
separate application mode that changes authentication and UI behavior.


Local Development
-----------------

The local Make targets intentionally separate "demo data exists" from "the app
is running in demo mode":

* ``make make-local-demo``
  Seeds the local database and bucket with the demo course, demo user, and demo
  movies.

* ``make run-local-debug``
  Starts Flask against the local dataset in **non-demo mode**. It explicitly
  clears ``DEMO_MODE`` and ``DEMO_COURSE_ID`` and prints a login link for the
  local admin user.

* ``make run-local-demo-debug``
  Starts Flask in **demo mode**. It sets ``DEMO_MODE=1`` and
  ``DEMO_COURSE_ID=demo-course`` before starting Flask. No login link is
  required because demo mode auto-authenticates as the demo user.


Rendering and UI
----------------

The server exposes demo mode to both Jinja and JavaScript:

* Jinja template variable: ``demo_mode``
* JavaScript global constant: ``demo_mode``

Templates can use Jinja conditionals to render a clear demo-mode indicator.
Client-side code can use the JavaScript constant to disable or hide controls.


Troubleshooting
---------------

PlantTracer stores login state in an ``api_key`` cookie. If you switch between
normal mode and demo mode in the same browser session, stale cookies can make
local testing confusing. If that happens, clear the browser cookie and reload.
