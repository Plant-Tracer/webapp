DynamoDB and Plant Tracer
============================

The Plant Tracer webapp uses AWS DynamoDB to store:

* The user list
* The course list
* The enrollment join table (which users are in which courses)
* The movie list
* The per-frame trackpoint annotations
* API keys and audit logs

Originally this was stored in a MySQL database. We migrated to DynamoDB for cost — most uses of
Plant Tracer can fit within the DynamoDB free tier, while the cost for running MySQL is upwards of
$50/month on AWS.

Each DynamoDB table is identified by an account and a table name. All table names share a common
prefix controlled by the ``DYNAMODB_TABLE_PREFIX`` environment variable (e.g. ``demo-``). For local
development you can use the `AWS DynamoDB local (downloadable version)
<https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/DynamoDBLocal.html>`_. We
recommend using the version downloaded as a JAR file.

The canonical table definitions are in ``src/app/schema.py``. All attribute-name constants are
defined at the top of ``src/app/odb.py``. Tables are created by ``odbmaint.create_tables()`` and
dropped by ``odbmaint.drop_tables()`` — used by ``make make-local-demo`` and the test fixtures.


Table Summary
-------------

All table names below are shown without the prefix. With ``DYNAMODB_TABLE_PREFIX=demo-`` the
``users`` table is named ``demo-users``, etc.

.. list-table::
   :header-rows: 1
   :widths: 20 40 20 20

   * - Table
     - Purpose
     - Partition Key
     - Sort Key
   * - ``users``
     - One record per registered user
     - ``user_id``
     - —
   * - ``unique_emails``
     - Enforces email address uniqueness across users
     - ``email``
     - —
   * - ``api_keys``
     - One record per issued API key (a user may have several)
     - ``api_key``
     - —
   * - ``courses``
     - One record per course
     - ``course_id``
     - —
   * - ``course_users``
     - Enrollment join table — which users are in which courses
     - ``course_id``
     - ``user_id``
   * - ``movies``
     - One record per uploaded movie
     - ``movie_id``
     - —
   * - ``movie_frames``
     - Per-frame trackpoint annotations
     - ``movie_id``
     - ``frame_number``
   * - ``logs``
     - Audit log entries
     - ``log_id``
     - —


Table Details
-------------

users
~~~~~

One record per registered user.

.. list-table::
   :header-rows: 1
   :widths: 25 15 60

   * - Attribute
     - Type
     - Description
   * - ``user_id``
     - String (PK)
     - Unique identifier, prefixed ``u`` for regular users, ``ud`` for admins
   * - ``email``
     - String
     - User's email address (unique, enforced via ``unique_emails``)
   * - ``user_name``
     - String
     - Display name; may be blank
   * - ``created``
     - Integer
     - Unix epoch seconds at registration
   * - ``enabled``
     - Integer (0/1)
     - Whether the account is active
   * - ``primary_course_id``
     - String
     - The course the user registered through; used as default context
   * - ``primary_course_name``
     - String
     - Denormalized name of the primary course
   * - ``courses``
     - List of strings
     - All courses the user is enrolled in
   * - ``admin_for_courses``
     - List of strings
     - Courses for which the user has admin privileges


api_keys
~~~~~~~~

One record per issued API key. A user may hold multiple keys (e.g. after re-sending a login link).
The key is sent as a cookie or POST parameter; the server validates it on every request.

.. list-table::
   :header-rows: 1
   :widths: 25 15 60

   * - Attribute
     - Type
     - Description
   * - ``api_key``
     - String (PK)
     - The key value, a random hex string
   * - ``user_id``
     - String
     - Owner of the key
   * - ``first_used_at``
     - Integer
     - Unix epoch seconds of first use (i.e. first login)
   * - ``last_used_at``
     - Integer
     - Unix epoch seconds of most recent use
   * - ``enabled``
     - Integer (0/1)
     - Whether the key is still valid

**GSI:** ``user_id_idx`` on ``user_id``. Used by ``DDBO.get_user_login_times()`` to aggregate
first/last login times across all of a user's keys without a table scan.


courses
~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 25 15 60

   * - Attribute
     - Type
     - Description
   * - ``course_id``
     - String (PK)
     - Unique identifier for the course
   * - ``course_name``
     - String
     - Human-readable course name
   * - ``course_key``
     - String
     - Registration passphrase that students use to self-enroll
   * - ``admins_for_course``
     - List of strings
     - ``user_id`` values of all admins for this course
   * - ``max_enrollment``
     - Integer
     - Maximum number of students allowed to self-register (default 50)


course_users
~~~~~~~~~~~~

A lightweight join table that records which users are enrolled in which courses. Each item has only
the two key attributes: ``course_id`` (partition key) and ``user_id`` (sort key).

Querying ``course_users`` by ``course_id`` returns all enrolled user IDs efficiently — this is used
by ``course_enrollments(course_id)`` in ``odb.py``.

``delete_user()`` removes the user's ``course_users`` rows for every course
listed on the user record. ``list_users_courses()`` still handles unknown
``course_users`` rows defensively because old or manually edited tables may
contain stale enrollment records.


movies
~~~~~~

One record per uploaded movie. Key attributes:

``movie_id``, ``title``, ``description``, ``user_id``, ``course_id``, ``published`` (0/1; defaults to 1 on creation),
``deleted`` (0/1), ``status``, ``total_frames``, ``fps``, ``width``, ``height``,
``movie_data_urn`` (S3 URN of the MP4), ``movie_zipfile_urn``, ``first_frame_urn``,
``last_frame_tracked``, ``research_use`` (0/1/None; None = not yet answered), ``credit_by_name`` (0/1/None; None = not yet answered), ``attribution_name``,
``rotation`` (0/90/180/270 degrees).

See ``src/app/schema.py`` ``Movie`` class for the full schema and constraints.


movie_frames
~~~~~~~~~~~~

Per-frame trackpoint storage. Keyed by ``(movie_id, frame_number)``.

Each record's ``trackpoints`` attribute is a list of objects with fields
``x``, ``y``, ``label``, ``frame_number``, ``status``, and ``err`` (all defined in the
``Trackpoint`` class in ``schema.py``).


Data Consistency Notes
----------------------

* **Email uniqueness** is enforced by a transactional write to both ``users`` and
  ``unique_emails`` at registration time.
* **Course admin list** (``admins_for_course`` on the course record) is kept in sync with
  ``admin_for_courses`` on the user record by ``add_course_admin()`` and
  ``remove_course_admin()``.
* **Enrollment** (``course_users`` rows) is added by ``register_email()`` and
  removed by ``delete_user()`` for the courses listed on the user record.
* **Login times** (``first_used_at``, ``last_used_at``) live on ``api_keys``, not ``users``.
  ``list_users_courses()`` aggregates them per user via the ``user_id_idx`` GSI.


Schema and Naming Changes
-------------------------

Some naming changes were made for clarity or to avoid conflicts with DynamoDB's reserved words.

.. list-table::
   :header-rows: 1
   :widths: 30 30 40

   * - Old name
     - New name
     - Reason
   * - ``name``
     - ``user_name``
     - ``name`` is a DynamoDB reserved word
