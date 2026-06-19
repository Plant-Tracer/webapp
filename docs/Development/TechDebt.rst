Technical Debt Review
=====================

Reviewed 2026-06-09 against the current source tree, Makefile, Lambda code,
tests, and Sphinx documentation. File counts are rough implementation estimates,
not exact diff sizes.

Easy / Fast
-----------

* Tighten movie access checks in ``odb.can_access_movie``.
  Impact: high; prevents course members from accessing another user's unpublished
  movies through direct API/Lambda calls. Files: 4-6.

* Validate upload preconditions before creating a movie.
  Impact: medium; returns a clear error when a user lacks ``primary_course_id``
  instead of raising a late ``KeyError``. Files: 3-5.

* Remove temporary upload debug logging and stale comments.
  Impact: low; reduces console noise and avoids leaking request-shape details in
  browser logs. Files: 2-4.

* Normalize small API response envelopes.
  Impact: low; makes endpoints such as ``/api/ver`` and Lambda errors easier for
  clients and tests to consume consistently. Files: 3-6.

* Replace isolated hard-coded API keys with existing symbols.
  Impact: low; reduces typo risk in request parsing and JSON responses without a
  broad model rewrite. Files: 4-8.

Medium
------

* Split ``src/app/odb.py`` by responsibility.
  Impact: medium; lowers risk in user/course/movie/log changes. Current hotspot:
  ``odb.py`` is about 1,767 lines. Files: 10-15.

* Move API request parsing into typed request/response models.
  Impact: medium; reduces raw form parsing and dict-as-structure usage in
  ``flask_api.py`` while keeping routes thin. Files: 8-12.

* Standardize frontend API access.
  Impact: medium; replaces scattered ``fetch``/``$.post`` calls and inline
  handlers with one small client layer and shared error handling. Files: 8-14.

* Add real local Lambda integration coverage for upload/analyze/retrace.
  Impact: high; exercises Flask, DynamoDB Local, MinIO, and the local
  ``lambda-resize`` bridge together. Files: 6-10.

* Replace movie-level retrace staleness with frame-range artifact validity.
  Impact: medium; ``needs_retracing`` is currently a coarse movie-level flag,
  but regional tracing and trimmed traced-MP4 exports need to distinguish the
  first stale frame, the stale end frame, and whether a full-movie or clipped
  traced artifact is current. Files: 5-9.

* Consolidate local setup docs and Make targets.
  Impact: medium; reduces drift across Mac, Ubuntu, and generic setup documents.
  Files: 5-8.

Long Term
---------

* Replace vendored Lambda app copies with a shared package.
  Impact: high; removes ``vend-lambda-resize`` drift and makes Flask/Lambda share
  versioned code through packaging. Files: 20-30.

* Return Pydantic models from data-access boundaries.
  Impact: high; moves from dict validation-on-write to typed read/write contracts
  for users, courses, movies, frames, and logs. Files: 25-40.

* Define a durable processing state machine.
  Impact: high; clarifies upload, ready, tracing, completed, failed, stale-lock,
  and retry behavior across Flask, Lambda, SQS/local queue, and UI polling.
  Files: 15-25.

* Rework authentication/session security.
  Impact: high; adds explicit token expiry/rotation behavior, cookie flags, CSRF
  posture, and clearer magic-link semantics. Files: 12-20.

* Componentize the browser application.
  Impact: medium-high; reduces global state and inline handlers in
  ``planttracer.js``/canvas controllers and creates a path to richer UI tests.
  Files: 25-50.

Reviewed Hotspots
-----------------

* Large files: ``src/app/odb.py`` (~1,767 lines), ``src/app/static/planttracer.js``
  (~1,072 lines), ``src/app/flask_api.py`` (~675 lines).
* Boundary risk: Flask and Lambda share code through ``vend-lambda-resize``.
* Data risk: DynamoDB items are mostly plain dicts after read, despite Pydantic
  schemas on write.
* Access risk: list filtering is stricter than direct movie access checks.
* Test risk: many JavaScript tests require mocks because runtime code depends on
  globals and inline browser handlers.
