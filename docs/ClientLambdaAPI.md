# Client Lambda API

The browser client calls the Lambda (lambda-resize) HTTP API for operations that require full frames or video: get-frame, get-movie-data (playback URL), tracking, rotate-and-zip, start-processing, new-frame. The VM (Flask/gunicorn) does not run tracking, serve frames, or serve movie playback URLs.

See [ArchitectureDesign.md](ArchitectureDesign.md) for the three principles: frames/video → lambda-resize, HTML → flask_app, metadata → flask_api.

## Lambda API base URL

The server injects the Lambda API base URL into every page via **base.html** so it is available to all JavaScript as the global **`LAMBDA_API_BASE`**:

- Set in the template from `get_lambda_api_base()` (see `apikey.page_dict()`).
- Example value: `https://your-lambda-api.example.com/`
- If not configured, the variable is empty and client code should skip Lambda calls (e.g. show “Lambda URL not configured”).

All client calls to the Lambda API are authorized: the client sends `api_key` (and other parameters) in the request; the Lambda validates `api_key` (e.g. via DynamoDB) before performing the operation.

## Endpoints used by the client

| Operation      | Method | Path / body | Purpose |
|----------------|--------|-------------|--------|
| Get frame     | GET    | `/api/v1/frame?api_key=...&movie_id=...&frame_number=...&size=...` | Single frame as JPEG |
| Get movie data| GET    | `/api/v1/movie-data?api_key=...&movie_id=...&format=zip` or `format=json` (optional) | Default: 302 redirect to signed S3 URL (movie). `format=zip`: 302 to zip. `format=json`: 200 JSON `{ "movie_id", "url" (MP4), "zip_url" (if present) }` for playback or download links. |
| Status        | GET    | `/status`   | Health check |
| Track movie   | POST   | `/api/v1`   | Body: `{ "action": "track-movie", "api_key", "movie_id", "frame_start" }` |
| New frame     | POST   | `/api/v1`   | Body: `{ "action": "new-frame", "api_key", "movie_id", "frame_number", "frame_base64_data"?(optional) }` |
| Rotate and zip| POST   | `/api/v1`   | Body: `{ "action": "rotate-and-zip", ... }` |
| Start processing | POST | `/api/v1`   | Body: `{ "action": "start-processing", ... }` |

## Tracking

Tracking is requested by POSTing to `LAMBDA_API_BASE + 'api/v1'` with JSON body:

- `action`: `"track-movie"`
- `api_key`: from the logged-in user (same as other API calls)
- `movie_id`: movie to track
- `frame_start`: the edited source frame (0-based). PlantTracer preserves this frame,
  deletes stored annotations for `frame_start + 1 ... end`, and resumes tracing at the
  following frame.

The Lambda validates `api_key`, resolves `user_id`, then runs tracking (writes trackpoints and zip to DynamoDB/S3). The client then polls for completion (e.g. via Flask `get-movie-metadata` with `get_all_if_tracking_completed`) and updates the UI.

## Where the variable is set

- **Template:** `src/app/templates/base.html` — declares `const LAMBDA_API_BASE = "{{ lambda_api_base }}";`
- **Server:** `src/app/apikey.py` — `page_dict()` sets `lambda_api_base` from `get_lambda_api_base()` so every page that uses the base template gets the same global.
