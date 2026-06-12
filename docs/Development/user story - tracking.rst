Upload And Track User Story
===========================

This page describes the current user workflow for upload, analysis, tracking,
and retracking.

Upload
------

1. User opens ``/upload``.
2. User enters title, description, research-use choice, attribution choice, and
   selects a movie file.
3. Browser computes SHA-256 and calls ``POST /api/new-movie``.
4. Flask creates a movie row and returns a presigned S3 POST.
5. Browser uploads the movie directly to S3/MinIO.
6. Browser loads frame 0 from ``GET /resize-api/v1/first-frame`` and offers an
   Analyze link.

Analyze
-------

1. User opens ``/analyze?movie_id=...``.
2. Browser gets metadata and frame 0.
3. User positions markers on the frame.
4. Browser saves marker trackpoints through
   ``POST /api/put-frame-trackpoints``.

Track Movie
-----------

1. User clicks Trace movie.
2. Browser posts to ``POST /resize-api/v1/trace-movie`` with:

   * ``x-api-key`` header
   * ``movie_id``
   * ``frame_start``

3. lambda-resize validates access, preserves the edited source frame, clears
   later trackpoints, marks the movie ``tracing``, and queues tracking.
4. Local mode uses the in-process local queue. Deployed mode uses SQS.
5. Worker writes trackpoints, frame ZIP, traced MP4, and final movie status.
6. Browser polls ``POST /api/get-movie-metadata`` until status is
   ``tracing completed``.

Retrack
-------

1. User navigates to the frame where tracking diverged.
2. User moves markers to the correct positions.
3. Browser saves that frame's trackpoints.
4. Browser posts ``frame_start`` for the edited frame to lambda-resize.
5. Tracking resumes at the following frame.

Download
--------

When tracking is complete, the user can download CSV trackpoints through
``POST /api/get-movie-trackpoints``.

Open Questions
--------------

* Whether future UI should support direct "go to frame N" controls.
* Whether variable-frame-rate movies need explicit timestamp support in addition
  to frame numbers.
* Whether the movie list should become server-rendered or stay browser-rendered.
