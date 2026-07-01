Backup and Restore
==================

This page specifies the Plant Tracer backup, restore, and course migration
tool, ``src/dbbackup.py``.

This is an operational backup for selected Plant Tracer data, not a full AWS
account snapshot. It is intended to run from a developer or administrator
machine with AWS credentials and a configured ``PLANTTRACER_S3_BUCKET``. The
target DynamoDB table prefix is specified on the command line and supersedes
``DYNAMODB_TABLE_PREFIX``. A future web-admin download/upload workflow may be
added later.

Goals
-----

``src/dbbackup.py`` supports:

* full and selective backups;
* full and selective restores;
* restoring a complete course, user, or movie dependency set;
* dry-run login-link generation for restored users, with sending only when
  ``--send`` is present;
* course and movie migration without leaving inconsistent DynamoDB records or
  stale S3 object references.

The implementation preserves existing IDs on restore. In particular,
``course_id``, ``user_id``, and ``movie_id`` are restored exactly as recorded in
the backup.

Command-Line Contract
---------------------

The CLI keeps backup, restore, inspection, login-link sending, and migration as
separate subcommands:

.. code-block:: text

   poetry run dbbackup backup --table-prefix PREFIX --output file.ptb [--all | --course-id C | --user-email E | --movie-id M] [--include-deleted]
   poetry run dbbackup restore --table-prefix PREFIX file.ptb [--all | --course-id C | --user-email E | --movie-id M] [--commit] [--regenerate-zips]
   poetry run dbbackup inspect file.ptb [--verbose]
   poetry run dbbackup list-prefixes
   poetry run dbbackup send-restore-links --table-prefix PREFIX file.ptb [--all | --course-id C | --user-email E] [--send]
   poetry run dbbackup migrate-course --table-prefix PREFIX --from-course-id A --to-course-id B [--user-email E] [--commit]

``--table-prefix`` is the authoritative table prefix for commands that touch
DynamoDB. It overrides ``DYNAMODB_TABLE_PREFIX`` if that environment variable is
also set.

``restore`` and ``migrate-course`` default to preflight mode. They must inspect
the target state and report planned writes or blockers, but they must not write
anything unless ``--commit`` is present.

``backup`` defaults to ``--all`` when no selector is supplied. Restore and
``send-restore-links`` require an explicit selector so operators choose the
restore or email scope deliberately.

``list-prefixes`` does not take ``--table-prefix``. It uses the current
DynamoDB connection settings, lists all tables, reports only prefixes for which
all application tables exist, and prints a fixed-width table with the course,
user, and movie counts plus a single UTC ``from``/``to`` range for each
complete prefix. The range is the
minimum and maximum timestamp found in user ``created`` fields, movie
``created_at``/``date_uploaded`` fields, optional movie ``status_updated_at``
fields, and optional course ``created``/``created_at`` fields when those
attributes are present. Current course rows do not have a schema-defined
creation timestamp, and frame/trackpoint rows store frame numbers rather than
timestamps. If the current AWS SSO token is expired, ``list-prefixes`` asks
whether it should run ``aws sso login`` and retry once.

Backup Scope
------------

Backups include application records needed to reconstruct courses, users,
movies, and movie annotations:

* ``users``
* ``courses``
* ``course_users``
* ``movies``
* ``movie_frames``

Backups do not include:

* ``api_keys``;
* ``unique_emails``;
* ``logs``;
* frame ZIP artifacts;
* original uploaded movie files, by default;
* traced movie artifacts.

Deleted movies are excluded by default. ``backup`` includes deleted movies only
when ``--include-deleted`` is present.

``unique_emails`` is regenerated during restore from restored user records.
``api_keys`` are intentionally not restored; after restore, the operator should
be able to send new login emails to every restored account, creating fresh API
keys. Audit logs are operational history and are not part of the backup. A
separate log-dump command should export logs to a syslog-like text file.

Movie Objects
-------------

Each backed-up movie includes the rotated and shrunk MP4 used for analysis.
This file is distinct from the traced MP4. The backup member name should be
based on the movie ID, for example ``movies/{movie_id}.mp4``.

Original uploaded movies are not included by default. If an implementation
later adds an explicit option to include originals, those files should be named
separately, for example ``movies/{movie_id}-orig.mp4``.

Frame ZIP files are not backed up because they can be large and can be
regenerated from the rotated and shrunk MP4. Restore should provide an option
to regenerate omitted ZIP files. The data model needs a separate
``needs_zipfile`` concept so a restored movie can distinguish "trackpoints are
stale and retracing is needed" from "trackpoints are current but the generated
ZIP artifact is missing."

Backup Format
-------------

The backup file extension is ``.ptb``. The file is a ZIP archive containing:

* a manifest JSON file;
* a human-readable ``README`` file;
* one JSON Lines file per backed-up DynamoDB table;
* one MP4 file per backed-up movie.

The archive layout should be:

.. code-block:: text

   manifest.json
   README
   tables/users.jsonl
   tables/courses.jsonl
   tables/course_users.jsonl
   tables/movies.jsonl
   tables/movie_frames.jsonl
   movies/{movie_id}.mp4

Each DynamoDB record is written as one JSON object per line using DynamoDB
AttributeValue JSON, matching the native DynamoDB API item shape. For example,
a string attribute is stored as ``{"S": "value"}`` and a number attribute is
stored as ``{"N": "10.0"}``. This preserves DynamoDB value types, including
decimal numbers, sets, binary values, booleans, nulls, lists, and maps.

The manifest records at least:

* backup format version;
* Plant Tracer application version;
* creation timestamp;
* operator identity, when available;
* source hostname or environment name, when available;
* source AWS account/region details, when available;
* source DynamoDB table prefix;
* source S3 bucket;
* selection filters used for the backup;
* backup options, including whether originals were included;
* per-table record counts;
* per-movie object names, sizes, and checksums.

The ``README`` must contain a full warning that the archive contains student
data, course data, movie metadata, trackpoint annotations, and movie files. It
must state that the archive is not password protected, should be stored and
transmitted as sensitive data, and can be restored into a Plant Tracer
deployment by an operator with suitable AWS credentials.

Selective Backup
----------------

Backup selection is separate from restore selection. Backup supports:

* all courses, users, and movies, which is the default when no selector is
  supplied;
* one course by ``course_id``;
* one user by email address;
* one movie by ``movie_id``.

A selective backup must include the dependency records needed to restore the
selected data consistently.

For a user backup, include the user, the user's primary course, every course
that contains one of the user's movies, the corresponding enrollment rows, the
user's selected movie rows, their frame rows, and their movie MP4 files.

For a movie backup, include only the movie owner user record, the movie's
course, the needed enrollment row, the movie row, frame rows, and movie MP4.
Do not include course administrator users solely because they administer the
movie's course.

Archive Inspection
------------------

``inspect`` defaults to a concise summary: manifest metadata, per-table record
counts, backed-up movie object count, and total backed-up movie bytes. It does
not dump individual records by default.

``inspect --verbose`` adds one-line summaries for each backed-up user, course,
course enrollment, movie, and movie object. Frame records are not dumped
individually. Instead, verbose inspection reports the total number of frame
records and groups consecutive frame ranges that have the same trackpoint
count and trackpoint labels, producing one line per trackpoint set.

Restore Behavior
----------------

Restore supports:

* all backed-up data;
* one course by ``course_id``;
* one user by email address;
* one movie by ``movie_id``.

Restore preserves IDs exactly. The target DynamoDB tables must already exist
under the specified ``--table-prefix``. Restore must not create tables.

Restore defaults to preflight mode. Without ``--commit``, it validates the
archive, validates target dependencies, reports blockers or planned changes to
stderr, and exits without writing DynamoDB records or S3 objects. Stderr is
enough for preflight failure reporting in the first implementation.

If any restored email address already exists in the target ``users`` table,
restore blocks before writing data. A future enhancement should allow movies
from the backup to be restored under the existing email address with a different
``user_id``. That remapping is out of scope for the first implementation.

Restore does not restore API keys. The ``send-restore-links`` command provides
a follow-up option to send fresh login emails to restored users. That
login-link command defaults to a dry run; it sends email only when ``--send``
is present.

Backup records a manifest warning that the backup may not be transactionally
consistent if the production app is active during backup. The implementation
does not force downtime because current utilization is low.

Regenerating ZIP Artifacts
--------------------------

Restore should provide an option to regenerate ZIP files after movie records
and MP4 objects are restored. Regeneration must use the same local/deployed
processing path used elsewhere in the project: Lambda through HTTP/SQS or the
local Lambda bridge. The restore path should not invent a separate video
processing implementation.

When ``--regenerate-zips`` is present, restore should enqueue regeneration work,
poll until completion, and print status to stderr once per second using ``\r``
to overprint the current line. It should emit a real newline every 30 seconds so
logs remain readable. ZIP regeneration times out after 5 minutes.

The current implementation accepts ``--regenerate-zips`` but fails closed with
an operator-facing error because the regeneration queue/polling integration has
not been implemented yet.

Course and Movie Migration
--------------------------

Course migration is part of ``src/dbbackup.py`` but is logically separate from
backup and restore.

Moving a user or course must update every field and index table needed to avoid
database inconsistency, including:

* user course lists and primary course fields where applicable;
* ``course_users`` rows;
* course admin lists when affected;
* movie ``course_id`` values;
* S3 object keys and all S3 URNs stored in movie records or frame records.

Plant Tracer S3 keys include ``course_id/movie_id``. Therefore migrating a
movie to a new course must move or copy its objects under the new course prefix
and rewrite the stored URNs. Leaving movie objects under the old course prefix
is not acceptable for the migration command. Course migration should completely
rewrite affected records to the new course ID rather than preserving the old
course ID as restore metadata.

Security and Privacy
--------------------

``.ptb`` files are not password protected in the first implementation. Operators
must treat them as sensitive student-data archives. The archive ``README`` must
make this explicit.

Because the backup includes movie files and metadata, it should be stored only
where student data is allowed, transmitted only over approved channels, and
deleted when it is no longer operationally needed.

Testing Requirements
--------------------

Backup and restore tests belong under the existing ``make pytest`` target.
Tests must use DynamoDB Local and MinIO through existing fixtures and Makefile
environment, not mocks.

The first substantive integration test:

* creates one course with one user and one movie;
* backs up that single course;
* verifies that restore without ``--commit`` performs preflight only;
* restores with ``--commit`` and verifies the restored DynamoDB records and MP4
  object match the source backup data;
* restores or migrates the same data to a different course and verifies that course
  references and S3 object keys are consistent.

``inspect`` is also covered so operators can view manifest data and counts
before running restore.

Open Follow-Ups
---------------

The first implementation depends on or is intentionally deferring these related
issues:

* `#1081 <https://github.com/Plant-Tracer/webapp/issues/1081>`_:
  distinguish missing ZIP artifacts from stale trace data.
* `#1082 <https://github.com/Plant-Tracer/webapp/issues/1082>`_:
  add a syslog-style audit log dump command.
* `#1083 <https://github.com/Plant-Tracer/webapp/issues/1083>`_:
  allow restore when the target email address already exists.

Documentation
-------------

When this feature is implemented, update at least:

* this page;
* :doc:`DynamoDB`, if table contents or restore ordering change;
* :doc:`S3`, if object layout or migration rules change;
* :doc:`EnvironmentVariables`, if new runtime variables are introduced;
* ``docs/ReleaseHistory.rst``.
