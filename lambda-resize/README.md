# lambda-resize

`lambda-resize` is the Plant Tracer video/frame/tracking service. It is deployed
as a Lambda HTTP API and can also run locally through `make run-local-lambda-debug`.

## HTTP Routes

- `GET /resize-api/v1/ping`
  Health check.

- `GET /resize-api/v1/first-frame?api_key=...&movie_id=...`
  Validate access, fetch the movie from S3/MinIO through a signed URL, apply
  saved rotation, scale to analysis size, and return frame 0 as JPEG.

- `GET /resize-api/v1/movie-data?api_key=...&movie_id=...`
  Return a 302 redirect to the signed original movie URL.

- `GET /resize-api/v1/movie-data?api_key=...&movie_id=...&format=json`
  Return JSON with signed movie and optional ZIP URLs.

- `GET /api/v1/movie-data?...`
  Compatibility route handled by the same movie-data function.

- `POST /resize-api/v1/trace-movie`
  Queue retracing. The API key is sent in the `x-api-key` header. The JSON body
  contains `movie_id` and `frame_start`.

## Queue Modes

- Local: `TRACKING_QUEUE_MODE=local` sends retrace work to an in-process queue
  drained by the local debug process.
- Deployed: `TRACKING_QUEUE_URL` points to SQS. SQS events are handled by the
  same Lambda entry point.

## Shared Code

The root Makefile vendors shared app modules into
`lambda-resize/src/resize_app/src/app/` through `make vend-lambda-resize`.
Lambda imports those files with `from .src.app ...`.

## Video Processing

Frame extraction, scaling, JPEG generation, and tracking use OpenCV (`cv2`) and
Pillow. ffmpeg is legacy/local tooling and is not the Lambda runtime path.

Tracking writes:

- frame trackpoints to DynamoDB,
- a frame ZIP to S3/MinIO,
- a traced MP4 to S3/MinIO,
- movie status and artifact URNs back to DynamoDB.

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
