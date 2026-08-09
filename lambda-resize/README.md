# lambda-resize

`lambda-resize` is the Plant Tracer video/frame/tracing service. It handles HTTP,
SQS, and S3 Object Created EventBridge invocations and can also run locally
through `make run-local-lambda-debug`.

## HTTP Routes

- `GET /resize-api/v1/ping`
  Health check. Returns `status`, request `time`, runtime `path`, application
  `app_version`, and `deployed_at`. Local runs report `deployed_at` as
  `unknown`; Makefile-driven SAM deploys stamp the deployed artifact with a UTC
  timestamp.

- `GET /resize-api/v1/first-frame?api_key=...&movie_id=...`
  Validate access, fetch the movie from S3/MinIO through a signed URL, apply
  saved rotation, scale to analysis size, and return frame 0 as JPEG.

- `GET /resize-api/v1/movie-data?api_key=...&movie_id=...`
  Return a 302 redirect to the signed original movie URL.

- `GET /resize-api/v1/movie-data?api_key=...&movie_id=...&format=json`
  Return JSON with signed movie and optional ZIP URLs.

- `POST /resize-api/v1/trace-movie`
  Queue retracing. The API key is sent in the `x-api-key` header. The JSON body
  contains `movie_id`, `frame_start`, and optionally `frame_end`.

- `POST /resize-api/v1/process-upload`
  Local MinIO compatibility adapter for the upload-completion service used by
  the deployed EventBridge handler. Production browsers do not call this route.

## Queue Modes

- Local: `TRACING_QUEUE_MODE=local` sends retrace work to an in-process queue
  drained by the local debug process.
- Deployed: `TRACING_QUEUE_URL` points to SQS. SQS events are handled by the
  same Lambda entry point. The queue carries retrace and post-upload jobs.

## Upload Events

Each deployed stack has an EventBridge rule matching the shared movie bucket
and only `uploads/{stack}/`. The handler validates the event, copies the exact-
size staging object to `movies/{stack}/`, deletes staging, and queues
post-upload metadata processing. Upload completion, resize start, and resize
completion are written to the DynamoDB `logs` table.

## Shared Code

The root Makefile vendors shared app modules into
`lambda-resize/src/resize_app/src/app/` through `make vend-lambda-resize`.
Lambda imports those files with `from .src.app ...`.

## Video Processing

Frame extraction, scaling, JPEG generation, and tracing use OpenCV (`cv2`) and
Pillow. ffmpeg is legacy/local tooling and is not the Lambda runtime path.

Tracing writes:

- frame trackpoints to DynamoDB,
- a frame ZIP to S3/MinIO,
- a traced MP4 to S3/MinIO,
- movie status and artifact URNs back to DynamoDB.

Optical flow may fail to resolve an individual marker in a low-texture frame.
The tracer carries that marker's last known position into the next frame so a
temporary miss does not delete it from the remainder of the trace.

Research-use and attribution metadata is embedded in traced MP4 output through
`mp4_metadata_lib`.

## Local Run

From the repository root:

```bash
make start-local-services
make make-local-demo
make run-local-lambda-debug
```

The local bridge listens on `http://127.0.0.1:9811/`.
