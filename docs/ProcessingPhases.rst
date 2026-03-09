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

  - Extend the movie list to show upload / processing / rotation status for each movie (e.g., ``uploading``, ``processing``, ``first-frame-ready``, ``zip-ready``, ``rotating``).
  - Improve messaging on the analyze page when processing is still running (poll for up to 60 seconds, then ask the user to return later).
  - Clarify first-frame behavior after upload (250ms polling with a clear error if the Lambda is not responding).

- Note (in comments/docs, not yet in code) that the movie list page should eventually be re-architected around server-side rendering with Jinja2; for now it continues to rely on the existing JSON APIs and client-side rendering.

