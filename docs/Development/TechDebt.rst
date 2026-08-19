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
  Impact: medium; returns a clear error when a user lacks a valid course context
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

* Replace plaintext API keys with hashed, user-addressable credentials (#1124).
  Impact: high; the current ``api_keys`` table uses the bearer token itself as
  its partition key, so a database read reveals a usable credential, and
  long-lived tokens are accepted in query strings. Move credentials into typed
  user child records, retaining only a salted verifier/hash plus lifecycle and
  per-key first/last-use fields. A credential must include a user ID and public
  credential ID so validation is one ``GetItem`` followed by verifier checking;
  do not scan a user's keys. Browser/API authentication must use a secure
  cookie or request header, while emailed magic links become short-lived,
  one-time handoffs. Files: 12-20.

* Retain sent email and provide a superadmin user-message drilldown (#1147).
  Impact: high; archive every exact outbound MIME message in private, encrypted
  S3 before delivery and create an immutable, typed email index item for the
  recipient. Record delivery attempts, including failures and dry runs. The
  admin UI must list a user's messages and authorize each full-message read;
  messages containing magic links are sensitive and must never expose a raw S3
  URL or be visible to ordinary users/course admins. Files: 10-18.

* Split ``src/app/odb.py`` by responsibility.
  Impact: medium; lowers risk in user/course/movie/log changes. Current hotspot:
  ``odb.py`` is about 1,767 lines. Files: 10-15.

* Move API request parsing into typed request/response models.
  Impact: medium; reduces raw form parsing and dict-as-structure usage in
  ``flask_api.py`` while keeping routes thin. Files: 8-12.

* Standardize frontend API access.
  Impact: medium; replaces scattered ``fetch``/``$.post`` calls and inline
  handlers with one small client layer and shared error handling. Files: 8-14.

* Standardize public API namespace versioning.
  Impact: medium; ``/api/*`` is the legacy unversioned Flask API surface while
  ``/resize-api/v1/*`` is the newer versioned Lambda resize service API. The
  asymmetry is understandable historically, but it confuses deployment smoke
  checks, client contracts, and future API design. Keep existing routes stable,
  document the legacy/new-service distinction, and introduce any future
  versioned web API path with explicit compatibility and migration rules. Files:
  5-10.

* Add real local Lambda integration coverage for upload/analyze/retrace.
  Impact: high; exercises Flask, DynamoDB Local, MinIO, and the local
  ``lambda-resize`` bridge together. Files: 6-10.

* Replace movie-level retrace staleness with frame-range artifact validity.
  Impact: medium; ``needs_retracing`` is currently a coarse movie-level flag,
  but regional tracing and trimmed traced-MP4 exports need to distinguish the
  first stale frame, the stale end frame, and whether a full-movie or clipped
  traced artifact is current. The current browser UI disables marker edits while
  that browser session is tracing, and when loaded metadata has
  ``status="tracing"``, but there is still no server-side lock: an edit from
  another tab with stale metadata or another client during Lambda tracing can
  race with Lambda's final ``needs_retracing=0`` write. Files: 5-9.

* Represent partial traces explicitly in graph data.
  Impact: low; graph labels currently cover the trimmed frame range and marker
  datasets use ``null`` where a marker is absent. For partially traced movies
  this can leave an empty gap at the right edge of the graph, but it preserves
  frame alignment across multiple marker datasets and is acceptable until graph
  exports gain richer trace-range metadata. Files: 2-4.

* Consolidate local setup docs and Make targets.
  Impact: medium; reduces drift across Mac, Ubuntu, and generic setup documents.
  Files: 5-8.

Long Term
---------

* Migrate ``users`` to a composite-key collection (#1148).
  Impact: high; the current table has only ``user_id`` as its key, so it cannot
  represent a profile plus independently queryable credentials and email audit
  records. Use ``PK=user_id`` with typed ``SK`` values such as ``PROFILE``,
  ``APIKEY#<credential-id>``, and ``EMAIL#<time>#<message-id>``. DynamoDB cannot
  add a sort key in place: create a replacement table and provide a tested
  dump, transform, backfill, count/checksum validation, canary, rollback, and
  cutover procedure for the small ``prod-`` and ``m1-`` datasets. Files: 15-25.

* Replace vendored Lambda app copies with a shared package.
  Impact: high; removes ``vend-lambda-resize`` drift and makes Flask/Lambda share
  versioned code through packaging. Files: 20-30.

* Return Pydantic models from data-access boundaries.
  Impact: high; moves from dict validation-on-write to typed read/write contracts
  for users, courses, movies, frames, and logs. Files: 25-40.

* Migrate movie-related DynamoDB records to a composite key schema (#758).
  Impact: high; the current ``movies`` table has only ``movie_id`` as its
  primary key, while ``movie_frames`` has the child-record shape we really need.
  The marker map currently uses the ``movie_frames`` metadata sentinel
  ``frame_number=-100``; this is clearer than overloading the ``movies``
  partition key but still mixes frame rows with movie metadata. Do not embed all
  frames in one movie item: high-frame movies can exceed DynamoDB's 400 KB item
  limit, create hot writes, and lose independently paged frame reads. Instead,
  use one logical movie collection with ``PK=movie_id`` and explicit typed sort
  keys such as ``METADATA``, ``MARKERS``, and ``FRAME#<number>`` (whether in one
  replacement table or two physical tables). DynamoDB cannot add a sort key to
  an existing table, so this requires a replacement/backfill with validation and
  rollback. Files: 10-20.

* Implement DynamoDB backup and selective restore.
  Impact: high; the S3 bucket is the long-term archive for movie objects, but
  there is no documented or implemented DynamoDB backup/restore system. Add a
  daily backup from DynamoDB to S3, plus a restore tool that can restore user
  accounts, courses, and movies selectively into any existing stack. A movie
  restore must include the movie metadata and its tracing data, including frame
  trackpoints. Files: 8-15.

* Define a durable processing state machine.
  Impact: high; clarifies upload, ready, tracing, completed, failed, stale-lock,
  and retry behavior across Flask, Lambda, EventBridge/local work, and UI
  polling.
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
