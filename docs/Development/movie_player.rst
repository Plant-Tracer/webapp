Movie Player Design
===================

The Analyze page is a browser-side canvas application. Flask serves the page and
metadata APIs; lambda-resize supplies video/frame data. New uploads are converted
into an immutable H.264 baseline/yuv420p analysis MP4, with every source frame in
order and no B-frames. The production analyzer uses ``mp4_frame_player.mjs`` for
forward/backward frame access; it does not download a JPEG ZIP.

The analyzer and completed-tracing metadata window support 50,000 frames. The
analyzer fetches marker metadata in 1,000-frame pages to bound HTTP responses.
Analyze reports an explicit error for larger movies instead of showing partial
annotations; the original upload and its complete derivative are preserved.
A ``pageshow`` event with ``persisted=true`` reloads the analyzer after browser
history restoration, reopening the disposed decoder and reacquiring its editing
lease. Normal navigation does not show a data-loss confirmation.

Tracing has a 30-second progress watchdog, renewed only when the last tracked
frame advances. Unchanged frames, failed requests and a hung request do not
extend it. On expiry the client aborts its status request, stops polling and warns
that server work may continue. Late replies cannot restart polling. A terminal
``tracing failed`` response stops immediately and displays its reason.

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

Static Frame-Stepping Demos
---------------------------

``/static/mp4player-demo1.html``
   Uses the native ``HTMLVideoElement`` and maps each source frame to one
   logical second. The demo movie is encoded at 15 FPS, so the controls seek by
   ``1 / 15`` seconds and display logical 1 FPS time.

``/static/mp4player-demo2.html``
   Uses Video.js with ``@douglassllc/videojs-framebyframe`` configured for
   the source movie's 15 FPS stream timing. The visible controls below the
   movie use Video.js playback and seek APIs so they match the native demo's
   logical 1 FPS behavior.

``/static/mp4player-demo3.html``
   Uses mp4box.js to extract MP4 samples, WebCodecs ``VideoDecoder`` to decode
   all source frames, and a canvas to render by frame index. This avoids native
   video seek rounding, but URL loading requires the MP4 server to allow CORS;
   the page also accepts a local MP4 file. Playback defaults to 15 FPS and can
   be adjusted from 0 to 60 FPS. The controls include first frame, previous
   frame, reverse playback, forward playback, next frame, and last frame.

Run ``make -C src/app/static serve`` from the repository root to serve the
standalone demos locally.

These demos are useful for comparing player behavior, but MP4 frame stepping is
still timestamp seeking. Browser decoders may seek from nearby keyframes,
especially when stepping backward. For frame-perfect random access, decode
frames outside the native player and render them to a canvas.

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

Single-Frame Browser Conformance Test
-------------------------------------

``make frame-step-browser-test`` reads four committed solid red, green, blue,
and yellow PPM frames plus their committed four-frame MP4 from
``browser_tests/fixtures/frame_step``.  A real Chrome/Chromium browser loads
``/static/mp4player-demo3.html`` and copies the decoded center pixel from that
page's canvas after every button click.  The test requires the exact sequence
``1, 2, 3, 4, 4, 3, 2, 1``; it fails if WebCodecs drops, duplicates, or
misorders a frame.  The MP4 uses an H.264 B-frame GOP, which exercises the
decoder timestamp path that is stricter on some Android and Windows devices.
The conformance workflow does not install or run FFmpeg; FFmpeg is needed only
when intentionally regenerating the committed MP4.

B-Frame Ordering
----------------

The WebCodecs player must not sort compressed B-frame samples into presentation
order inside an MP4 file.  A B-frame can depend on a later reference frame, so
``mp4player-demo3.html`` first orders the demuxed samples by their decoding
timestamp (``dts``) before passing them to ``VideoDecoder``.  Each
``EncodedVideoChunk`` retains its composition timestamp (``cts``), because the
WebCodecs timestamp is the frame's presentation timestamp.  After decoding,
the player orders ``VideoFrame`` objects by that presentation timestamp for the
frame-step controls.

This separates the two orderings that a B-frame stream requires:

* decode compressed samples by ``dts``;
* display decoded frames by ``cts``.

If a target device cannot decode the source stream even with that ordering,
produce a compatibility asset by re-encoding rather than reordering MP4
packets.  For example:

.. code-block:: console

   ffmpeg -i input.mp4 -c:v libx264 -bf 0 -g 30 -pix_fmt yuv420p -c:a copy output-no-b-frames.mp4

``-bf 0`` removes B-frames.  The command changes the video bitstream and is
therefore an explicit compatibility transcode; it is not a lossless MP4
metadata edit.

The ``Frame-step browser conformance`` GitHub Actions workflow runs the probe
on macOS Chrome, Windows Chrome, and Android Chrome in an emulator.  It is a
required regression signal for a change to the MP4 single-frame implementation;
a platform is supported only when its corresponding job passes.

Portable Analysis-MP4 Bundle
----------------------------

``make analysis-mp4-bundle`` creates a manual-test directory for an arbitrary
local MP4. It uses the same Python encoder service that Lambda will use for the
analysis derivative: rotation is applied once, the frame fits within the chosen
analysis dimensions (enlarging small sources as needed), and every output frame
has its zero-based frame number burned into the upper-right corner. The MP4 uses a fixed 15 FPS H.264
``yuv420p`` baseline profile with P-frames and no B-frames.

For example:

.. code-block:: console

   make analysis-mp4-bundle \\
     ANALYSIS_MP4_INPUT=/path/to/capture.mp4 \\
     ANALYSIS_MP4_OUTPUT=/tmp/capture-player \\
     ANALYSIS_MP4_ROTATION=90

The new output directory contains ``capture_scaled.mp4``, ``index.html``, a
local ``mp4box.all.js`` demuxer, a metadata manifest, and ``README.txt``.
``index.html`` has no Flask, API-key, ZIP, CDN, or build-step dependency. Copy
the complete directory to a static web server with ``scp`` and open
``index.html`` over HTTP or HTTPS. Do not use ``file:`` URLs because browser
module and fetch rules vary by platform.

``make analysis-mp4-browser-test`` validates the generated bundle through a
real local Chrome browser. It checks the rendered four-frame sequence forward
and backward before a bundle is used for manual testing.


Frame Numbers, Traces, and Recoding
-----------------------------------

Every frame index is zero-based, including red analysis labels, player controls,
marker ranges, API parameters, spreadsheets, and blue download labels. Frame 0
is capture time zero; frame N is N times the capture interval, regardless of
playback FPS or trimming. Old analysis derivatives are regenerated once on demand
using encoder version 2. Previously downloaded files remain unchanged.

The analyzer draws all saved path segments: segments ending at or before the
current frame are opaque and 2 pixels wide; later segments have 50 percent
opacity and are 1 pixel wide. Missing frames do not create connecting lines.
The marker table lists each saved marker's first
and last frame even when it has no location at the current frame (shown as n/a).

Recoding preserves the established coordinate height, including legacy videos
that were enlarged to 640 pixels. If saved points have no recorded height, stored
frame images can establish it; otherwise recoding stops with a diagnostic rather
than guessing. Movies already containing mixed coordinate spaces require an
explicit data repair; coordinates must not be rescaled indiscriminately.

Tracing starts after the selected seed frame. Earlier frames are read to render
the download, but their points and tracing progress are not rewritten. Downloads
use a blue frame/time label; elapsed seconds appear only when capture timing is
known, never inferred from the playback frame rate.
