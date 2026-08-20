# Flask API Reference

REST endpoints served by the Plant Tracer Flask application are mounted under
`/api/`. Most are defined in `src/app/flask_api.py`; admin-specific endpoints
are defined in `src/app/admin_api.py`. This document covers authentication,
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

- `/api/ver` returns `{"__version__": "...", "git_commit": "...", "sys_version": "...", "stack_name": "...", "DYNAMODB_TABLE_PREFIX": "..."}`.
- `/api/get-movie-trackpoints` returns CSV by default.

```text
{ "error": false, ... }
{ "error": true, "message": "Human-readable reason" }
```

---

## Endpoints

### Admin

#### `GET /api/admin/summary`

Return the minimal read-only admin landing-page data. This endpoint backs `/admin`
and is intentionally read-only.

**Authorization**

- `superadmin` and `superauditor` users receive the cross-course view.
- Course administrators receive a view limited to courses they administer,
  users enrolled in those courses, and movies assigned to those courses. A
  visible user's memberships and default course are also limited to that
  administered-course scope.
- Regular users receive HTTP 403. Course-admin access does not depend on a
  `superadmin` or `superauditor` existing.

**Query parameters**

| Name | Required | Description |
|------|----------|-------------|
| `limit` | No | Page size for each requested course, user, or movie list. Defaults to 25, maximum 100. |
| `section` | No | Return rows for `all` (default), `courses`, `users`, or `movies`. A table-specific value leaves the other two item lists empty so clients can page each table without redundant scans. |
| `course_marker` | No | Opaque, course-table-bound restart marker from the previous `courses.restart_marker`. |
| `user_marker` | No | Opaque, user-table-bound restart marker from the previous `users.restart_marker`. |
| `movie_marker` | No | Opaque, movie-table-bound restart marker from the previous `movies.restart_marker`. |

Unknown sections and malformed, non-object, or wrong-table restart markers
receive HTTP 400.

**Response**

```json
{
  "error": false,
  "viewer": {
    "user_id": "u...",
    "user_name": "Course Admin",
    "email": "teacher@example.edu",
    "super_role": "none",
    "all_courses": false,
    "course_ids": ["PlantTracer 101"]
  },
  "counts": { "courses": 1, "users": 2, "movies": 3 },
  "courses": {
    "items": [
      {
        "course_id": "PlantTracer 101",
        "course_key": "spring-beans-2026",
        "course_name": "Intro Biology",
        "enrollment_count": 42,
        "max_enrollment": 100,
        "admin_count": 1,
        "created_at": 1784800000,
        "last_movie_activity_at": null
      }
    ],
    "restart_marker": null
  },
  "users": {
    "items": [
      {
        "user_id": "u...",
        "user_name": "Alice",
        "email": "alice@example.edu",
        "default_course_id": "PlantTracer 101",
        "super_role": "none",
        "created_at": 1784800100,
        "last_movie_activity_at": null,
        "courses": [
          {
            "course_id": "PlantTracer 101",
            "is_admin": false
          }
        ]
      }
    ],
    "restart_marker": null
  },
  "movies": {
    "items": [
      {
        "movie_id": "m...",
        "title": "Bean Growth",
        "course_id": "PlantTracer 101",
        "user_id": "u...",
        "owner_name": "Alice",
        "state": "published",
        "status": "ready",
        "created_at": 1784800200,
        "uploaded_at": 1784800300,
        "last_activity_at": 1784800400,
        "total_frames": 1441,
        "total_bytes": 12500000,
        "fpm": "60",
        "has_traced_movie": true,
        "description": "Daily bean measurement",
        "fps": "30",
        "width": 640,
        "height": 480,
        "rotation": 0,
        "trim_start_frame": 0,
        "trim_end_frame": 1440,
        "needs_retracing": false,
        "research_use": 1,
        "credit_by_name": "Alice",
        "attribution_name": "Alice"
      }
    ],
    "restart_marker": null
  }
}
```

For a course administrator, `viewer.all_courses` is `false`,
`viewer.course_ids` contains the administered course IDs, and all three counts
and result lists describe only that scope. Restart markers remain opaque and
table-bound for global readers; for course administrators they page the
corresponding scoped result set.

The movie list includes published, hidden, and deleted DynamoDB records. The
API continues to use the ``published`` field: ``1`` is published and ``0`` is hidden.
The admin summary reports the same states as ``published``, ``hidden``, or
``deleted``.
`state` reports that visibility/deletion state; `status` reports processing state.
The summary deliberately omits object URNs and API keys. The default table view
stays compact: its `Verbose details` control reveals stable IDs, named course
administrators, and movie metadata including description, dimensions, trimming,
rotation, retrace state, and research attribution. ``GET /api/admin/movies/<movie_id>/storage-health``
loads the verbose-only per-object storage health and pending-upload age on demand.
Storage health reports only ``present``, ``missing``, or ``not created`` and never
exposes raw S3 URIs. Course enrollment counts are
read consistently from the `course_users` table. User memberships and movies
carry `course_id`; the admin page joins those IDs to the separately downloaded
course names after all bounded pages arrive.
The same browser-side join derives each course's first upload and latest movie
activity and each user's latest movie activity. A course's displayed creation
date uses `created_at`, falling back to its first movie upload for legacy rows.
Movies without `uploaded_at` are pending uploads and are displayed with a red
background. Movie elapsed time is `(total_frames - 1) / fpm`; encoded playback
`fps` is deliberately not used.
DynamoDB scan order is not stable. The admin page requests bounded pages until
all three tables are loaded, then sorts complete result sets in the browser;
clients must treat restart markers as opaque. Course rows include the registration
`course_key`; callers must treat it as a secret because anyone with the key can
request enrollment in that course. The admin page masks each course key by default;
its per-row eye control reveals or hides the value without changing it.
Admin table columns have visible drag/keyboard resize handles. Course links open
`/list?course_id=...` in a new tab without changing the user's persisted default
course. Movie rows use a visible `⋮` menu for play, traced download, and—for
`superadmin` only—Analyze.

#### `GET /api/admin/movies/{movie_id}/media`

Return fresh five-minute signed URLs for the original movie and, when present,
the traced movie. The response does not expose stored S3 URNs. Both
`superauditor` and `superadmin` may use this authenticated, read-only endpoint
for any movie. Course administrators may use it only for movies in courses they
administer; ordinary membership in another course is not sufficient.

```json
{
  "error": false,
  "movie_id": "m...",
  "play_url": "https://...",
  "traced_download_url": "https://..."
}
```

### User & Registration

#### `PATCH /api/default-course`

Change the signed-in user's profile default. The selected course must
already be present in that user's course memberships. The endpoint uses the
existing authentication cookie and does not grant course membership.
``PATCH /api/current-course`` is a temporary compatibility alias.

**JSON request**

```json
{ "course_id": "PlantTracer 101" }
```

**Success response**

```json
{
  "error": false,
  "course": {
    "course_id": "PlantTracer 101",
    "course_name": "Intro Biology"
  }
}
```

An invalid or non-member course receives HTTP 400. Missing authentication
receives HTTP 403.

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

### Course context

Authenticated browser requests that operate on course data send ``course_id``.
The server validates that course against the authenticated user's memberships.
For reads, an omitted or deleted course falls back to the profile's valid
``default_course_id`` and then to the first valid membership. Mutations reject a
deleted explicit course with HTTP 409, and all operations reject an existing
course outside the caller's authority with HTTP 403.

The pull-down stores the active course in tab-scoped ``sessionStorage``. It does
not update the user profile. ``PATCH /api/default-course`` with
``{"course_id": "..."}`` is the explicit operation for changing the profile
default. ``PATCH /api/current-course`` remains a compatibility alias during the
migration.

#### `POST /api/list-users`
#### `POST /api/list-users-courses`

Both routes are equivalent. Return users and courses visible to the caller.

**Behavior by role**

- **Admin:** Returns users enrolled in the requested administered course.
- **Non-admin:** Returns only the caller's own record for the resolved course.

**Response**

```text
{
  "error": false,
  "users": [
    {
      "user_id": "u...",
      "user_name": "Alice",
      "email": "alice@example.com",
      "default_course_id": "PlantTracer-101",
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
video file to a deployment-scoped staging key. The row initially has
`created_at`, `upload_staging_urn`, and the durable `movie_data_urn`, but not
`uploaded_at`. In AWS, an S3 Object Created EventBridge event makes
lambda-resize verify the exact byte count, move the object to its durable key,
record upload metadata, and queue post-upload processing. In local MinIO mode,
the browser invokes the authenticated `/resize-api/v1/process-upload`
compatibility adapter. The browser polls metadata until processing is complete,
then requests the first frame and links the user to Analyze.

**Parameters**

| Name | Required | Description |
|------|----------|-------------|
| `api_key` | Yes | Must not be the demo key |
| `title` | No | Movie title |
| `description` | No | Movie description |
| `movie_data_sha256` | Yes | SHA-256 hex digest of the video file (64 chars) |
| `movie_data_length` | Yes | Exact movie byte length, from 1 through the configured upload limit. The returned S3 policy accepts exactly this size. |
| `research_use` | No | `"1"` = yes, `"0"` = no, omit = not answered |
| `credit_by_name` | No | `"1"` = yes, `"0"` = no, omit = not answered (only meaningful when `research_use=1`) |
| `attribution_name` | No | Attribution name (only stored when `credit_by_name=1`) |
| `fpm` | No | Capture interval in frames/minute (time-lapse). Positive number, fractional allowed; stored on the movie and included as `x-amz-meta-fpm` in the presigned post |

**Response**

```text
{
  "error": false,
  "movie_id": "m...",
  "presigned_post": {
    "url": "https://s3.amazonaws.com/...",
    "fields": { ... }
  },
  "upload_completion_mode": "eventbridge"
}
```

`upload_completion_mode` is `eventbridge` in deployed AWS stacks and `http` in
local MinIO development.

---

#### `POST /api/list-movies`

List all movies visible to the caller. An optional `course_id` selects one
course for the tab; the caller must be a member or have a
`superauditor`/`superadmin` read role. The query does not alter the user's
default course. A missing deleted course falls back to the valid default.

**Response**

```text
{ "error": false, "movies": [ { "movie_id": "m...", "title": "...", ... } ] }
```

Each movie dict contains all DynamoDB metadata fields. In addition, if the movie has a traced MP4 stored in S3 (`movie_traced_urn` starts with `s3:`), the response injects a short-lived presigned URL. Clients should treat `needs_retracing=1` as user-visible only when this URL is present; before the first traced MP4 exists there is no stale traced artifact to warn about.

| Field | Description |
|-------|-------------|
| `movie_traced_url` | Presigned S3 URL for downloading the traced MP4; only present when a traced MP4 exists |

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

While an active trace lease exists, metadata has `status: "tracing"` and a
`tracking_lock` object with `acquired_at` and `started_by_user_name`. Clients
use this to present Analyze as read-only.

An active browser analysis lease adds `analysis_lock` with `active`, `owned`,
`acquired_at`, and `started_by_user_name`. `owned` is true only when the
request includes the holder's `analysis_lease_id`.

---

#### `POST /api/acquire-movie-analysis-lease`

Acquire Analyze's movie-row lease immediately on page entry. The successful
holder receives an opaque `lease_id`. When another browser already holds the
lease, this still returns HTTP 200 with `lease_id: null` and an `analysis_lock`
object so the caller can display Analyze as view-only.

`POST /api/heartbeat-movie-analysis-lease` renews the holder's lease, and
`POST /api/release-movie-analysis-lease` releases it on page exit. Both require
`api_key`, `movie_id`, and `analysis_lease_id`.

---

#### `POST /api/get-movie-trackpoints`

Download all trackpoints for a movie as CSV (default), XLSX, or JSON.

**Parameters**

| Name | Required | Description |
|------|----------|-------------|
| `api_key` | Yes | |
| `movie_id` | Yes | |
| `format` | No | `"xlsx"` for an Excel workbook, `"json"` for JSON; omit for CSV |

**Response:** CSV with columns `frame_number`, `<label> x (<unit>)`, `<label> y (<unit>)` for each marker label, served with `Content-Type: text/csv` and `Content-Disposition: attachment; filename="trackpoints.csv"` so the browser downloads it rather than displaying it inline.

With `format=xlsx`, returns an Excel workbook served with `Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` and `Content-Disposition: attachment; filename="trackpoints.xlsx"`. The workbook contains:

- `Trackpoints`: the same columns, values, trim filtering, and unit conversion as the CSV export.
- `Metadata`: export context including movie id, title, trim bounds, exported frame count, marker count, coordinate origin, inferred frame height, calibration status, units, scale, and capture interval (`fpm`) when available.
- `Markers`: one row per marker label with marker type (`apex`, `ruler`, `inflection point`, or `marker`), graphable status, color, marker id, ruler size, undeletable status, frame range, trackpoint count, and any status/error values found in exported trackpoints.
- `Chart Data`: displacement from each graphable marker's first exported position, using frames as the x-axis or minutes when `fpm` is set. Ruler markers are excluded from chart data.
- `Charts`: native Excel line charts for X Position and Y Position, backed by `Chart Data`.

**Units (#763):** each value column header is annotated with its unit, `(mm)` or `(px)`:

- `Ruler XXmm` marker columns are **always** in pixels (`(px)`).
- Other markers' columns are in **millimeters** (`(mm)`, value × scale) when the analysis is
  ruler-calibrated — i.e. there are ≥ 2 `Ruler XXmm` markers and the lowest and highest are both
  off their default positions; otherwise they are in pixels (`(px)`). The scale is derived from
  the lowest and highest ruler markers in the first trimmed frame (mirrors the Analyze marker
  table). mm values are rounded to 2 decimals.

With `format=json`: `{ "error": "False", "trackpoint_dicts": [...] }` — JSON values are raw pixel coordinates (no unit conversion).

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

**Side effect:** sets `needs_retracing=1` on the movie record. This flag indicates that a previously traced MP4 may now be stale. The client uses it to show the retracing warning when `movie_traced_url` is also present.

The tracer UI disables marker editing and reset actions while a trace request is active in that browser session, and when loaded movie metadata has `status="tracing"`. This prevents normal same-session marker edits while Lambda is tracing, so Lambda does not finish by clearing `needs_retracing` for a traced MP4 computed from an earlier marker state.

Returns HTTP 409 when an active trace lease makes the movie read-only, or when
another browser owns the active analysis lease. The same rule applies to marker
rename, trim, and capture-interval writes; the owning browser includes its
`analysis_lease_id` with those requests.

---

#### `POST /api/rename-marker`

Rename one marker label across all stored trackpoints for a movie. Other marker properties, such as coordinates, color, `undeletable`, status, and error metadata, are preserved.

**Parameters**

| Name | Required | Description |
|------|----------|-------------|
| `api_key` | Yes | Must not be the demo key |
| `movie_id` | Yes | |
| `old_label` | Yes | Existing marker label to rename |
| `new_label` | Yes | New marker label. Must not already exist on the movie. |

**Response**

```json
{ "error": false, "frames_updated": 3, "trackpoints_updated": 3 }
```

**Side effect:** when any stored trackpoints are renamed, sets `needs_retracing=1` on the movie record. Marker labels are stored in the `movie_frames` marker-map item at `frame_number=-100`, so rename updates that marker map and does not rewrite each frame record.

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

```text
{ "error": false, "metadata": { "movie_id": "m...", "trim_start_frame": 0, "trim_end_frame": 42, ... } }
```

Returns HTTP 400 with `error: true` if both or neither trim frame parameter is provided, or if
the resulting trim bounds are invalid (e.g. `trim_start_frame > trim_end_frame`).

---

#### `POST /api/set-movie-fpm`

Set the capture interval (frames/minute) for a movie. Owner or course admin only.
Editing this value only rescales the Analyze time axis and Rate statistics; it does
not require retracing. See `docs/Development/AnalysisResults.rst`.

**Parameters**

| Name | Required | Description |
|------|----------|-------------|
| `api_key` | Yes | Must not be the demo key |
| `movie_id` | Yes | |
| `fpm` | Yes | Capture interval in frames/minute. Positive number, fractional allowed (e.g. `0.5`) |

**Response**

```text
{ "error": false, "metadata": { "movie_id": "m...", "fpm": "30", ... } }
```

Returns HTTP 400 with `error: true` if `fpm` is missing, non-numeric, not positive, or above the
allowed maximum.

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
the API defaults to the caller's own `log_user_id`. Course administrators and
super read roles may request course-wide logs. Other course members remain
restricted to their own logs even when they supply `course_id`.

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

Return the application version and the source commit embedded in the Lambda-web
artifact. No authentication required. `git_commit` is a full 40-character SHA
for deployed Lambda artifacts; local Flask runs return `unavailable`.

**Response**

```text
{ "__version__": "0.9.7.6.2", "git_commit": "857d5637ee1949eb5bc883875eee9e7b562cd8f5", "sys_version": "3.12.x ...", "stack_name": "prod", "DYNAMODB_TABLE_PREFIX": "prod-" }
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
