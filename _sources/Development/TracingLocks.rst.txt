Tracing locks
=============

Only one tracing job may modify a movie at a time. The DynamoDB ``movies`` row
is the durable source of truth. It stores a random job ID, the initiating
user, acquisition time, heartbeat, and a renewable 15-minute expiry. A stale
lease is deliberately handled by application reads and conditional writes:
when the expiry is older than 15 minutes, it is ignored and the next trace
request atomically replaces it. No TTL is used, because TTL can only delete a
whole DynamoDB item and the movie must remain durable.

Analyze leases
--------------

Opening Analyze immediately acquires a separate, renewable 15-minute analysis
lease on that same movie row. The normal browser can edit; a later browser is
explicitly view-only and sees the existing holder's name and start time. The
holder releases its lease when leaving the page, while a heartbeat and expiry
recover from crashes or lost connectivity. Flask requires the opaque lease ID
on marker, trim, and capture-interval writes, so client-side disabled controls
cannot bypass ownership.

Starting a trace atomically replaces the initiating browser's analysis lease
with the tracing lease. A trace cannot begin while another browser owns the
analysis lease, and an old page's release request cannot remove a tracing
lease or a newer browser's lease.

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
rejected by the Flask API. The active Analyze page polls movie metadata,
displays frame progress, and loads the results when tracing completes. The
progress message also tells the user that it is safe to leave the page and
reopen Analyze later.

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
#. A movie-row lease with a job token, owner, heartbeat, and expiry is
   selected. It makes SQS redelivery and stale-lock recovery safe without
   another table, and keeps the movie as the single source of truth.
#. A dedicated DynamoDB lease table would make ownership distinct, but adds an
   unnecessary table and lookup for data that belongs to the movie.
#. FIFO SQS could serialize queue delivery, but cannot protect the pre-queue
   mutation or replace a database concurrency boundary.
