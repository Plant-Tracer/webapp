# Client Lambda API

The browser calls the lambda-resize HTTP API for operations that require video
or frame access. Flask owns HTML and metadata APIs; lambda-resize owns first
frame extraction, playback URL generation, and retracing.

See [ArchitectureDesign.md](ArchitectureDesign.md) for the current service
boundary.

## Lambda API Base URL

Flask injects the Lambda API base URL into pages as the browser global
`LAMBDA_API_BASE`.

- Template: `src/app/templates/base.html`
- Server: `src/app/apikey.py`, via `get_lambda_api_base()`
- Local override: `PLANTTRACER_LAMBDA_API_BASE=http://127.0.0.1:9811/`
- Deployed same-origin stack: `https://{stack}.planttracer.com/`
- Fallback when no explicit base is configured: `https://{HOSTNAME}.{DOMAIN}/`,
  or the current request origin when those variables are absent.

All client calls are authorized. The browser sends the current `api_key`; the
Lambda validates it against DynamoDB.

Static JavaScript and CSS are not part of `LAMBDA_API_BASE`; they are served
same-origin by Flask/`lambda-web` under `/static/*` until there is a versioned
asset plan for external static hosting.

## Endpoints

| Operation | Method | Path | Auth | Purpose |
|-----------|--------|------|------|---------|
| Ping | GET | `/resize-api/v1/ping` | none | Health check; returns `{ "error": false, "status": "ok", ... }` with `app_version`, `deployed_at`, and selected stack parameters. |
| Complete upload (local adapter) | POST | `/resize-api/v1/process-upload` | `x-api-key` header | Completes a MinIO staging upload through the same service used by the AWS EventBridge handler. |
| First frame | GET | `/resize-api/v1/first-frame?api_key=...&movie_id=...` | query `api_key` | Returns JPEG frame 0 with saved rotation applied and scaled to the analysis size. |
| Movie data | GET | `/resize-api/v1/movie-data?api_key=...&movie_id=...&format=json` | query `api_key` | Returns signed playback/download URLs as JSON. |
| Movie data redirect | GET | `/resize-api/v1/movie-data?api_key=...&movie_id=...` | query `api_key` | 302 redirect to signed movie URL. |
| Movie zip redirect | GET | `/resize-api/v1/movie-data?api_key=...&movie_id=...&format=zip` | query `api_key` | 302 redirect to signed frame ZIP URL if present. |
| Trace movie | POST | `/resize-api/v1/trace-movie` | `x-api-key` header | Queues retracing from a user-edited source frame through an optional end frame. |

## Complete Upload Request

`POST /resize-api/v1/process-upload`

```text
x-api-key: <api_key>
Content-Type: application/json
```

```json
{ "movie_id": "m..." }
```

This is a local-development compatibility adapter for MinIO. Deployed browsers
do not call it; S3 Object Created events reach lambda-resize through
EventBridge. The caller must be allowed to edit the movie. Lambda-resize reads
the staging object with `HeadObject`, rejects a missing object or a byte count
different from `upload_bytes_expected`, copies it to the durable key, records
upload metadata, deletes staging, and starts post-upload processing. Read-only
superauditors cannot complete or otherwise mutate movies; superadmins can.

The EventBridge invocation is not a public HTTP endpoint. Its Pydantic envelope
validation additionally checks the event source/type, bucket, deployment
prefix, course/movie identifiers, and corresponding DynamoDB row.

## Trace Movie Request

`POST /resize-api/v1/trace-movie`

Headers:

```text
x-api-key: <api_key>
Content-Type: application/json
```

Body:

```json
{ "movie_id": "m...", "frame_start": 12, "frame_end": 200 }
```

`frame_start` is the edited source frame. Plant Tracer preserves that frame,
clears stored trackpoints after it through `frame_end` when supplied, marks the
movie as `tracing`, and dispatches work. In local mode the work goes to the
in-process queue; in deployed mode a stack-scoped EventBridge rule pushes the
custom work event to lambda-resize without idle polling.

## Local Development

Use the Makefile instead of hand-built commands:

```bash
make run-local-lambda-debug
make run-local-debug
```

`run-local-lambda-debug` starts a Flask bridge that converts local HTTP requests
into API Gateway v2 events and calls `resize_app.main.lambda_handler()`.
