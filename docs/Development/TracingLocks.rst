Tracing locks
=============

Only one tracing job may modify a movie at a time. A DynamoDB
``movie_trace_locks`` row is the durable source of truth. It contains the
movie ID, a random job ID, the initiating user, acquisition time, heartbeat,
and a renewable 15-minute expiry. DynamoDB TTL eventually removes abandoned
rows, but application reads and conditional writes enforce expiry immediately.

Trace lifecycle
---------------

The trace request atomically obtains the lease and changes the movie status to
``tracing``. It then clears later frames and enqueues an SQS message containing
the job ID. A worker may claim a queued job exactly once; SQS redelivery is a
no-op. The worker renews its lease while writing frames. Completion or a caught
exception conditionally publishes the terminal movie state and deletes only
the lease with its own job ID. Failures use ``tracing failed`` and retain a
safe failure summary.

Metadata and user interface
---------------------------

Movie-list and movie-metadata responses include an active lock's start time
and initiating user's display name. Analyze is read-only while the lock is
active: viewing, playback, and downloads remain available, while marker,
trim, retrace, and capture-interval writes are disabled in the browser and
rejected by the Flask API. Analyze does not poll for tracing completion; the
user reopens Analyze later.

Audit and diagnostics
---------------------

The DynamoDB audit table records structured ``movie.tracing.started``,
``movie.tracing.completed``, and ``movie.tracing.failed`` events with the job
ID and a sanitized error summary. CloudWatch retains the full Lambda traceback
and operational telemetry. The audit table is not a replacement for CloudWatch
because its entries are user-facing and must not contain secrets or raw stack
traces.

Alternatives considered
-----------------------

#. A conditional movie ``status`` transition was smaller, but did not carry
   ownership or make an SQS redelivery safe.
#. A status-plus-job-token design avoided another table but mixed business
   status with lease ownership and recovery mechanics.
#. A dedicated DynamoDB lease table was selected: it makes ownership, expiry,
   and the initiating user explicit while keeping movie status durable and
   visible.
#. FIFO SQS could serialize queue delivery, but cannot protect the pre-queue
   mutation or replace a database concurrency boundary.
