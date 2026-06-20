# Flask API Reference

All REST endpoints served by the Plant Tracer Flask application are defined in
`src/app/flask_api.py` and mounted at `/api/`. This document covers authentication,
the standard response envelope, and every endpoint.

For the Lambda (frame/video processing) endpoints, see [ClientLambdaAPI.md](ClientLambdaAPI.md).

---

## Authentication

Most endpoints require an `api_key` parameter. Pass it as a POST body field or
a query-string parameter.

Unauthenticated endpoints:

- `GET|POST /api/ver`
- `GET|POST /api/config-check`
- `GET|POST /api/register`
- `GET|POST /api/resend-link`

- Valid key -> request proceeds, user identity resolved from the key.
- Invalid or missing key on authenticated API routes -> `{"error": true, "message": "Invalid api_key"}` with HTTP 403.

API keys are issued per-user and stored in the `api_keys` DynamoDB table. A user may hold
multiple keys (e.g. after re-sending a login link). Keys are sent as a cookie after first login.

---

## Response Envelope

Most endpoints return JSON with `"error": false` on success or `"error": true`
plus `"message"` on failure. Exceptions:

- `/api/ver` returns `{"__version__": "...", "sys_version": "..."}`.
- `/api/get-movie-trackpoints` returns CSV by default.

```text
{ "error": false, ... }
{ "error": true, "message": "Human-readable reason" }
```

---

## Endpoints

### User & Registration

#### `POST /api/register`

Register a new user by email address and course key. Sends a login link by email.

**Parameters**

| Name | Required | Description |
|------|----------|-------------|
| `email` | Yes | Email address to register |
| `course_key` | Yes | Course registration passphrase |
| `name` | No | User's display name |
| `planttracer_endpoint` | No | Base URL for login link in email (defaults to server hostname) |

**Response**

```json
{ "error": false, "message": "Registration key sent to alice@example.com ...", "user_id": "u..." }
```

Returns `error: true` if the email is invalid, the course key is invalid, or the course is full.
Returns `error: true` (but still registers the user) if the mailer is not configured.

---

#### `POST /api/resend-link`

Resend a login link to an already-registered email address.

**Parameters**

| Name | Required | Description |
|------|----------|-------------|
| `email` | Yes | Email address of the existing user |
| `planttracer_endpoint` | No | Base URL for login link in email |

**Response**

```json
{ "error": false, "message": "If you have an account, a link was sent. ..." }
```

Always returns the same message regardless of whether the email exists (prevents enumeration).

---

#### `POST /api/bulk-register`

Register multiple users at once. Requires the caller to be a course admin.

**Parameters**

| Name | Required | Description |
|------|----------|-------------|
| `api_key` | Yes | Must belong to an admin of `course_id` |
| `course_id` | Yes | Target course |
| `email-addresses` | Yes | Newline-delimited list of email addresses. Also accepts comma- or semicolon-delimited values. |
| `names` | No | Newline-delimited list of display names, positionally matched to `email-addresses`. |
| `planttracer_endpoint` | No | Base URL for login links in emails |

**Response**

```json
{
  "error": false,
  "message": "Registered 3 email address(es) and sent login links.",
  "user_ids": ["u...", "u...", "u..."]
}
```

If the mailer is not configured, users are registered but `message` will note the email failure.

---

#### `POST /api/check-api_key`

Validate an API key and return the associated user record.

**Response**

```text
{ "error": false, "userinfo": { "user_id": "u...", "email": "...", ... } }
```

---

### User Listing

#### `POST /api/list-users`
#### `POST /api/list-users-courses`

Both routes are equivalent. Return users and courses visible to the caller.

**Behavior by role**

- **Admin:** Returns all users enrolled in every course the caller admins, sorted by
  `primary_course_id`. Also returns all those courses in the `courses` list.
- **Non-admin:** Returns only the caller's own user record and their enrolled courses.

**Response**

```text
{
  "error": false,
  "users": [
    {
      "user_id": "u...",
      "user_name": "Alice",
      "email": "alice@example.com",
      "primary_course_id": "PlantTracer-101",
      "courses": ["PlantTracer-101"],
      "admin_for_courses": [],
      "first": 1714000000,
      "last":  1714500000
    }
  ],
  "courses": [
    { "course_id": "PlantTracer-101", "course_name": "Intro Biology", ... }
  ]
}
```

`first` and `last` are Unix epoch seconds of the user's first and most recent login, respectively
(aggregated across all their API keys). Both are `null` if the user has never logged in.

---

### Movies

#### `POST /api/new-movie`

Create a movie record and obtain a presigned S3 POST URL for uploading the
video file directly to its final S3 key. After upload, the browser requests the
first frame from lambda-resize and links the user to Analyze.

**Parameters**

| Name | Required | Description |
|------|----------|-------------|
| `api_key` | Yes | Must not be the demo key |
| `title` | No | Movie title |
| `description` | No | Movie description |
| `movie_data_sha256` | Yes | SHA-256 hex digest of the video file (64 chars) |
| `research_use` | No | `"1"` = yes, `"0"` = no, omit = not answered |
| `credit_by_name` | No | `"1"` = yes, `"0"` = no, omit = not answered (only meaningful when `research_use=1`) |
| `attribution_name` | No | Attribution name (only stored when `credit_by_name=1`) |

**Response**

```text
{
  "error": false,
  "movie_id": "m...",
  "presigned_post": {
    "url": "https://s3.amazonaws.com/...",
    "fields": { ... }
  }
}
```

---

#### `POST /api/list-movies`

List all movies visible to the caller (their own movies and published movies in their course; admins additionally see unpublished movies from other users in their course).

**Response**

```text
{ "error": false, "movies": [ { "movie_id": "m...", "title": "...", ... } ] }
```

---

#### `POST /api/get-movie-metadata`

Get metadata and optionally per-frame trackpoints for a specific movie.

**Parameters**

| Name | Required | Description |
|------|----------|-------------|
| `api_key` | Yes | |
| `movie_id` | Yes | |
| `frame_start` | No | First frame number to return trackpoints for |
| `frame_count` | No | Number of frames (required if `frame_start` is provided; must be ≥ 1) |
| `get_all_if_tracking_completed` | No | If `"1"` and tracking is complete, return all frames |

**Response**

```text
{
  "error": false,
  "metadata": { "movie_id": "m...", "title": "...", "status": "...", ... },
  "frames": {
    "0": { "markers": [ { "x": 100.0, "y": 200.0, "label": "Apex", ... } ] }
  }
}
```

`frames` is only present when `frame_start` is provided.

---

#### `POST /api/get-movie-trackpoints`

Download all trackpoints for a movie as CSV (default) or JSON.

**Parameters**

| Name | Required | Description |
|------|----------|-------------|
| `api_key` | Yes | |
| `movie_id` | Yes | |
| `format` | No | `"json"` for JSON; omit for CSV |

**Response:** CSV with columns `frame_number`, `<label> x`, `<label> y` for each marker label, served with `Content-Type: text/csv` and `Content-Disposition: attachment; filename="trackpoints.csv"` so the browser downloads it rather than displaying it inline.
With `format=json`: `{ "error": "False", "trackpoint_dicts": [...] }`.

---

#### `POST /api/put-frame-trackpoints`

Write trackpoints for a single frame. Used by the client before requesting re-tracking.

**Parameters**

| Name | Required | Description |
|------|----------|-------------|
| `api_key` | Yes | Must not be the demo key |
| `movie_id` | Yes | |
| `frame_number` | Yes | Zero-based frame index |
| `trackpoints` | Yes | JSON array of trackpoint objects: `[{"x": 100.0, "y": 200.0, "label": "Apex"}, ...]` |

**Response**

```json
{ "error": false, "message": "trackpoints recorded: 2 " }
```

---

#### `POST /api/rotate-movie`

Set the movie's rotation. Tracking is cleared; Lambda applies the rotation when re-processing.

**Parameters**

| Name | Required | Description |
|------|----------|-------------|
| `api_key` | Yes | Must not be the demo key |
| `movie_id` | Yes | |
| `rotation` | Yes | Degrees: `0`, `90`, `180`, or `270` |

**Response**

```json
{ "error": false }
```

---

#### `POST /api/delete-movie`

Delete or undelete a movie.

**Parameters**

| Name | Required | Description |
|------|----------|-------------|
| `api_key` | Yes | Must not be the demo key |
| `movie_id` | Yes | |
| `delete` | No | `"1"` (default) to delete, `"0"` to undelete |

**Response**

```json
{ "error": false }
```

---

#### `POST /api/set-research-metadata`

Set `research_use` (and optionally `credit_by_name`) for a movie. Only the movie's uploader may call this endpoint — course admins are not permitted to change another user's research metadata. When `research_use` is set to anything other than `"1"`, `credit_by_name` is automatically cleared server-side; `attribution_name` is left intact.

**Parameters**

| Name | Required | Description |
|------|----------|-------------|
| `api_key` | Yes | Must belong to the movie's uploader |
| `movie_id` | Yes | Movie to update |
| `research_use` | No | `"1"` = yes, `"0"` = no, omit = not answered |
| `credit_by_name` | No | `"1"` = yes, `"0"` = no; only applied when `research_use=1` |

**Response**

```text
{ "error": false }
```

---

#### `POST /api/set-movie-trim`

Set one inclusive trim bound for a movie. Exactly one of `trim_start_frame` or
`trim_end_frame` must be provided per call.

**Parameters**

| Name | Required | Description |
|------|----------|-------------|
| `api_key` | Yes | Must not be the demo key |
| `movie_id` | Yes | |
| `trim_start_frame` | Cond. | Zero-based first frame to include in trim (provide this or `trim_end_frame`, not both) |
| `trim_end_frame` | Cond. | Zero-based last frame to include in trim (inclusive; provide this or `trim_start_frame`, not both) |

**Response**

```json
{ "error": false, "metadata": { "movie_id": "m...", "trim_start_frame": 0, "trim_end_frame": 42, ... } }
```

Returns HTTP 400 with `error: true` if both or neither trim frame parameter is provided, or if
the resulting trim bounds are invalid (e.g. `trim_start_frame > trim_end_frame`).

---

#### `POST /api/set-metadata`

Set a single metadata property on a movie or user record.

**Parameters**

| Name | Required | Description |
|------|----------|-------------|
| `api_key` | Yes | |
| `set_movie_id` | Cond. | Movie to update (provide this or `set_user_id`) |
| `set_user_id` | Cond. | User to update (provide this or `set_movie_id`) |
| `property` | Yes | Property name to set |
| `value` | Yes | New value |

---

### Logging

#### `POST /api/get-logs`

Return audit log entries. At least one index filter is required by the database
layer (`log_user_id`, `course_id`, or `ipaddr`). If the request provides none,
the API defaults to the caller's own `log_user_id`.

**Parameters** (all optional filters)

`start_time`, `end_time`, `course_id`, `course_key`, `movie_id`, `log_user_id`, `ipaddr`,
`count`, `offset`

**Response**

```text
{ "error": false, "logs": [ { "log_id": "...", "time_t": 1714000000, ... } ] }
```

#### `POST /api/get-log`

Legacy route that calls `odb.get_logs(user_id=get_user_id())` with no request
filters. Because the database function requires an index filter, prefer
`/api/get-logs`.

---

### Infrastructure

#### `GET|POST /api/ver`

Return the application version. No authentication required.

**Response**

```text
{ "__version__": "0.9.7.6.2", "sys_version": "3.12.x ..." }
```

---

#### `GET|POST /api/config-check`

Check DynamoDB connectivity, S3 CORS configuration, and S3 bucket region. No authentication required.

**Response**

```json
{
  "dynamodb_ok": true,  "dynamodb_message": "...",
  "cors_ok": true,      "cors_message": "...",
  "bucket_region_ok": true, "bucket_region_message": "..."
}
```
