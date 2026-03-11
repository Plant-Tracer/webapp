PlantTracer Movie Processing Phases
===================================

This note sketches the staged refactor of movie upload and processing.

Phase 1 – Infra / Bootstrap / Events
------------------------------------

- Remove the S3 → Lambda event architecture for the ``uploads/`` prefix:

  - Delete the ``LambdaS3InvokePermission`` resource in ``template.yaml`` so S3 no longer invokes the Lambda directly.
  - Stop configuring S3 bucket notifications in ``etc/bootstrap.sh`` (drop the call to ``etc/s3_upload_trigger.py``).
  - Remove the bootstrap S3-based ping that uploads ``uploads/_bootstrap/ping.json`` and instead rely on the Lambda HTTP ``/status`` endpoint for health checks.

- Lambda remains reachable only via its HTTP API (AWS::Serverless::HttpApi); no behavior change for existing HTTP routes in this phase.

- Update docs and rules that describe the S3 → Lambda trigger so they reflect the HTTP-only model.

Phase 2 – Flask / JavaScript Orchestration
------------------------------------------

- Change the upload pipeline to:

  - Have the browser call a status API to confirm the Lambda is healthy before starting an upload.
  - Use the upload API to create the movie record and mark its status as ``uploading``.
  - Upload movies directly to their final S3 keys via presigned POST (no ``uploads/`` staging prefix).
  - After a successful upload, have the browser call a new Lambda processing API to kick off processing.

- On the server side (Flask):

  - Simplify ``/api/new-movie`` to always presign the final key instead of choosing between staging and final based on environment.
  - Add or expose movie-level processing state in the movies table (e.g., ``processing_state``, ``first_frame_urn``, ``movie_zipfile_urn``).
  - Move movie rotation from VM ffmpeg into a Lambda-driven API that queues rotation/processing commands.

- In the browser:

  - Wire the upload page to use the new status and start-processing APIs.
  - After upload, initiate processing and poll for the first frame and zipfile readiness using the new state fields.

Phase 3 – UI Refinements and Status Display
-------------------------------------------

- Make movie processing state visible and understandable in the UI:

  - Extend the movie list to show upload / processing / rotation status for each movie (e.g., ``uploading``, ``processing``, ``first-frame-ready``, ``zip-ready``, ``rotating``). **Done:** list shows ``processing_state`` in the Status column.
  - Improve messaging on the analyze page when processing is still running (poll for up to 60 seconds, then ask the user to return later). **Done:** ``#firsth2`` shows "Waiting for processing to complete…" while polling; on timeout "Processing did not complete in time. Please come back later."
  - Clarify first-frame behavior after upload (250ms polling with a clear error if the Lambda is not responding). **Done:** 250ms × 10 attempts; clear error message and no broken image icon.

- Note (in comments/docs and code): the movie list page should eventually be re-architected around server-side rendering with Jinja2; for now it continues to rely on the existing JSON APIs and client-side rendering. **Done:** comment in ``flask_app.py`` at ``/list`` and in ``planttracer.js`` at ``list_movies_data``.

Rotation and zip behavior (Phase 2)
-----------------------------------

To avoid queuing multiple rotation requests when the user clicks "Rotate" several times, the client **debounces** rotate clicks: the user may click 1, 2, or 3 times (for 90°, 180°, or 270°); after about one second with no further click, the client sends a **single** request to ``/api/edit-movie`` with ``action=rotate90cw`` and ``rotation_steps=1|2|3``. The server applies that many 90° rotations in one go, updates the stored movie, then starts building the frame zip in a **background thread**. The request returns as soon as rotation is done; zip creation continues in the background.

The user can go to the Analyze page immediately. The first frame shown comes from the already-rotated movie (via the get-frame API). They can place markers (drag points) on that frame. The zip file is being created in the background; when it becomes available, the analyze page **polls** ``get-movie-metadata`` every 2 seconds. When ``movie_zipfile_url`` appears, the page loads the zip and switches to the full frame set so the user can scrub through all frames. If the zip does not appear within 60 seconds, the page shows "Zip still not ready. Please come back later." This behavior is consistent with the existing test infrastructure (edit-movie tests; analyze flow uses the same APIs).

Rotation in Lambda (no ffmpeg)
------------------------------

Rotation and zip creation can run in the Lambda instead of the VM. The Lambda does **not** use the ffmpeg binary (which would add ~150MB to the deployment). It uses **PyAV (av)** and **Pillow** only: decode video with av, rotate each frame with Pillow, re-encode with av (mpeg4), and build the frame zip by encoding each frame as JPEG and writing to a zip. All dependencies are already in the Lambda group (``poetry group lambda``). The VM still supports rotation (ffmpeg) when the Lambda is not configured (e.g. local dev).

Lambda-only code and testing
-----------------------------

The Lambda can depend on code and packages that the main Flask API does not (e.g. ``resize_app/rotate_zip.py``, PyAV). The single ``pyproject.toml`` at repo root defines group ``lambda`` for Lambda-only deps; ``make install-lambda-deps`` (or ``poetry install --with lambda``) installs everything needed to build and run the Lambda. For testing: run the Lambda handler locally with mock HTTP events, or add a second Lambda later and ensure CI runs ``install --with lambda`` and any Lambda-specific tests. See ``lambda-resize/Makefile`` (vend-app, install) and the root Makefile targets for lambda-resize.

