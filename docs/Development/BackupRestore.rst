Backup and Restore
==================

This page specifies the planned Plant Tracer backup, restore, and course
migration tool. The implementation target is a new developer command-line
program, ``src/dbbackup.py``.

This is an operational backup for selected Plant Tracer data, not a full AWS
account snapshot. It is intended to run from a developer or administrator
machine with AWS credentials and a configured ``PLANTTRACER_S3_BUCKET``. The
target DynamoDB table prefix is specified on the command line and supersedes
``DYNAMODB_TABLE_PREFIX``. A future web-admin download/upload workflow may be
added later.

Goals
-----

``src/dbbackup.py`` should support:

* full and selective backups;
* full and selective restores;
* restoring a complete course, user, or movie dependency set;
* optional regeneration of omitted movie ZIP artifacts after restore;
* course and movie migration without leaving inconsistent DynamoDB records or
  stale S3 object references.

The first implementation should preserve existing IDs on restore. In
particular, ``course_id``, ``user_id``, and ``movie_id`` are restored exactly as
recorded in the backup.

Command-Line Contract
---------------------

The CLI should keep backup, restore, inspection, login-link sending, and
migration as separate subcommands:

.. code-block:: text

   src/dbbackup.py backup --table-prefix PREFIX --output file.ptb [--all | --course-id C | --user-email E | --movie-id M] [--include-deleted]
   src/dbbackup.py restore --table-prefix PREFIX file.ptb [--all | --course-id C | --user-email E | --movie-id M] [--commit] [--regenerate-zips]
   src/dbbackup.py inspect file.ptb
   src/dbbackup.py send-restore-links --table-prefix PREFIX file.ptb [--all | --course-id C | --user-email E] [--send]
   src/dbbackup.py migrate-course --table-prefix PREFIX --from-course-id A --to-course-id B [--user-email E] [--commit]

``--table-prefix`` is the authoritative table prefix for commands that touch
DynamoDB. It overrides ``DYNAMODB_TABLE_PREFIX`` if that environment variable is
also set.

``restore`` and ``migrate-course`` default to preflight mode. They must inspect
the target state and report planned writes or blockers, but they must not write
anything unless ``--commit`` is present.

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

Each DynamoDB record is written as one JSON object per line. The serializer must
round-trip DynamoDB values such as ``Decimal`` values without changing their
logical type.

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

Backup selection is separate from restore selection. Backup should support:

* all courses, users, and movies;
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

Restore Behavior
----------------

Restore should support:

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

Restore must not restore API keys. It should provide a follow-up option to send
fresh login emails to restored users. That login-link command defaults to a dry
run; it sends email only when ``--send`` is present.

Restore should warn that the backup may not be transactionally consistent if
the production app is active during backup. The first implementation does not
need to force downtime because current utilization is low.

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

The first substantive integration test should:

* create one course with one user and one movie;
* back up that single course;
* verify that restore without ``--commit`` performs preflight only;
* restore with ``--commit`` and verify the restored DynamoDB records and MP4
  object match the source backup data;
* restore or migrate the same data to a different course and verify that course
  references and S3 object keys are consistent.

``inspect`` should also be covered in the first implementation so operators can
view manifest data and counts before running restore.

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
