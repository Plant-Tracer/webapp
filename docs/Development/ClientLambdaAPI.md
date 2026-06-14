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
- Deployed fallback: `https://{HOSTNAME}-lambda.{DOMAIN}/`

All client calls are authorized. The browser sends the current `api_key`; the
Lambda validates it against DynamoDB.

## Endpoints

| Operation | Method | Path | Auth | Purpose |
|-----------|--------|------|------|---------|
| Ping | GET | `/resize-api/v1/ping` | none | Health check; returns `{ "error": false, "status": "ok", ... }`. |
| First frame | GET | `/resize-api/v1/first-frame?api_key=...&movie_id=...` | query `api_key` | Returns JPEG frame 0 with saved rotation applied and scaled to the analysis size. |
| Movie data | GET | `/resize-api/v1/movie-data?api_key=...&movie_id=...&format=json` | query `api_key` | Returns signed playback/download URLs as JSON. |
| Movie data redirect | GET | `/resize-api/v1/movie-data?api_key=...&movie_id=...` | query `api_key` | 302 redirect to signed movie URL. |
| Movie zip redirect | GET | `/resize-api/v1/movie-data?api_key=...&movie_id=...&format=zip` | query `api_key` | 302 redirect to signed frame ZIP URL if present. |
| Trace movie | POST | `/resize-api/v1/trace-movie` | `x-api-key` header | Queues retracing from a user-edited source frame. |

Compatibility route:

- `GET /api/v1/movie-data` calls the same handler as `/resize-api/v1/movie-data`.

## Trace Movie Request

`POST /resize-api/v1/trace-movie`

Headers:

```text
x-api-key: <api_key>
Content-Type: application/json
```

Body:

```json
{ "movie_id": "m...", "frame_start": 12 }
```

`frame_start` is the edited source frame. Plant Tracer preserves that frame,
clears stored trackpoints after it, marks the movie as `tracing`, and queues
work. In local mode the work goes to the in-process queue; in deployed mode it
goes to SQS through `TRACKING_QUEUE_URL`.

## Local Development

Use the Makefile instead of hand-built commands:

```bash
make run-local-lambda-debug
make run-local-debug
```

`run-local-lambda-debug` starts a Flask bridge that converts local HTTP requests
into API Gateway v2 events and calls `resize_app.main.lambda_handler()`.
