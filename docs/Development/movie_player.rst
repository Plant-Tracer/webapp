Movie Player Design
===================

The Analyze page is a browser-side canvas application. Flask serves the page and
metadata APIs; lambda-resize supplies video/frame data.

Runtime Inputs
--------------

The base template injects these browser globals:

* ``API_BASE`` - Flask API base.
* ``LAMBDA_API_BASE`` - lambda-resize HTTP API base.
* ``api_key`` - current login token.
* ``user_id`` - current user.
* ``demo_mode`` - whether mutating UI actions should be disabled.
* ``MAX_FILE_UPLOAD`` - upload size limit.

Frame And Playback APIs
-----------------------

``GET /resize-api/v1/first-frame``
   Returns frame 0 as JPEG after API-key validation, saved rotation, and
   analysis-size scaling.

``GET /resize-api/v1/movie-data``
   Returns or redirects to signed S3 URLs for original movie playback and the
   optional frame ZIP.

``POST /resize-api/v1/trace-movie``
   Queues retracing after the browser saves edited trackpoints through Flask.

``POST /api/get-movie-metadata``
   Returns stored movie metadata and, when requested, frame trackpoints.

``POST /api/put-frame-trackpoints``
   Stores marker positions for a single frame before retracing.

Client Classes
--------------

``CanvasController``
   Owns the HTML canvas, zoom state, drawing, hit detection, and draggable items.

``CanvasMovieController``
   Extends canvas behavior with frame loading and playback controls.

``TracerController``
   Coordinates markers, marker table, tracking/retracking actions, graph data,
   and server persistence.

State Variables
---------------

* ``movie_id`` - movie being analyzed.
* ``total_frames`` - number of known frames.
* ``last_frame_tracked`` - latest tracked frame stored by the server.
* ``current_frame`` - frame currently displayed.
* ``tracking`` - true while retracing is in progress.
* ``playing`` - true while playback is advancing frames.
* ``frames`` - cached frame data from ZIP entries or Lambda frame URLs.

Retrace Flow
------------

1. User moves markers on frame ``N``.
2. Browser posts the edited frame's trackpoints to Flask.
3. Browser posts ``movie_id`` and ``frame_start=N`` to lambda-resize.
4. lambda-resize preserves frame ``N``, clears later trackpoints, and queues
   tracking from ``N + 1``.
5. Browser polls Flask metadata until status becomes ``tracing completed``.
6. Browser reloads frame/trackpoint data and re-enables controls.

Invariants
----------

* ``playing`` and ``tracking`` are not true at the same time.
* ``0 <= current_frame < total_frames`` when ``total_frames`` is known.
* ``last_frame_tracked`` is absent or between ``0`` and ``total_frames - 1``.
* Marker coordinates are stored per frame in DynamoDB ``movie_frames`` rows.
