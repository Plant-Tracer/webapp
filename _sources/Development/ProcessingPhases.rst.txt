Plant Tracer Movie Processing
=============================

This page describes the current upload, first-frame, playback, and retrace
workflow. Historical phase plans have been collapsed into the live behavior.

Upload
------

1. The browser computes a SHA-256 digest for the selected movie.
2. The browser posts metadata to ``POST /api/new-movie``.
3. Flask creates a DynamoDB movie row with status ``uploading`` and returns a
   presigned S3 POST for the final object key.
4. The browser uploads the movie directly to S3/MinIO with the returned form
   fields.
5. The upload page requests the first frame from lambda-resize and links the
   user to Analyze.

There is no S3 ``uploads/`` staging prefix and no S3 bucket notification path.
Lambda is invoked by HTTP or SQS/local queue.

First Frame
-----------

The browser requests:

.. code-block:: text

   GET LAMBDA_API_BASE/resize-api/v1/first-frame?api_key=...&movie_id=...

lambda-resize validates the API key, signs the movie S3 URL, extracts frame 0,
applies saved rotation, scales the frame to the analysis size, and returns a
JPEG.

Playback
--------

The movie list requests:

.. code-block:: text

   GET LAMBDA_API_BASE/api/v1/movie-data?api_key=...&movie_id=...&format=json

The compatibility route returns signed movie and optional ZIP URLs. The browser
sets the video element source to the signed movie URL so playback bytes come
from S3/MinIO.

Retracing
---------

1. The user edits markers on frame ``N``.
2. The browser saves frame ``N`` trackpoints through Flask
   ``POST /api/put-frame-trackpoints``.
3. The browser posts to lambda-resize:

   .. code-block:: text

      POST /resize-api/v1/trace-movie
      x-api-key: <api_key>

   .. code-block:: json

     { "movie_id": "m...", "frame_start": 12, "frame_end": 200 }

4. lambda-resize clears trackpoints after frame ``N``, marks the movie as
   ``tracing``, and queues the work.
5. In local mode, ``TRACING_QUEUE_MODE=local`` sends work to the in-process
   queue. In deployed mode, ``TRACING_QUEUE_URL`` sends work to SQS.
6. The worker traces from frame ``N + 1`` through optional ``frame_end``, writes trackpoints to DynamoDB,
   writes a ZIP and traced movie to S3/MinIO, and marks status as
   ``tracing completed``.
7. The browser polls ``/api/get-movie-metadata`` until completion.

Local Process Model
-------------------

Use two local processes:

.. code-block:: bash

   make run-local-lambda-debug
   make run-local-debug

``run-local-debug`` starts Flask on port 8080 and ensures a local Lambda
endpoint is available. ``run-local-lambda-debug`` starts the local HTTP bridge
on port 9811 and the local retrace worker.

Video Processing Library
------------------------

Current lambda-resize frame extraction, scaling, JPEG generation, and tracing
use OpenCV (``cv2``) and Pillow. ffmpeg is legacy/local tooling, not the
Lambda runtime path.
