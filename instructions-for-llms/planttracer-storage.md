# PlantTracer Storage Model

This note documents what PlantTracer keeps in DynamoDB and what remains in object storage so future code changes do not assume hidden tracing state.

## DynamoDB

PlantTracer stores structured metadata in DynamoDB:

- `movies`
  - Per-movie metadata such as `movie_id`, ownership, title/description, upload timestamps, rotation, `total_frames`, `total_bytes`, `last_frame_tracked`, and the S3/MinIO URNs for the original movie, traced movie, and frame zipfile.
  - The `status` field is lightweight per-movie progress metadata. There is no separate tracing job table.
- `movie_frames`
  - One row per frame number that may contain:
    - `frame_number`
    - optional `frame_urn`
    - `trackpoints` for that frame
- `users`, `api_keys`, `courses`, `course_users`, `logs`
  - Standard account, authorization, course, and audit data.

## Not Stored In DynamoDB

PlantTracer does not keep any separate DynamoDB documents for:

- interpolation state between frames
- optical-flow working state
- cached exported JSON payloads
- rendered frame overlays
- traced MP4 bytes
- frame zip bytes
- separate tracing-job rows or completion documents

Derived media artifacts live in S3/MinIO and are referenced from the `movies` table by URN.

## Retrace Semantics

When a user edits frame `N` and asks PlantTracer to retrace from that frame:

- frame `N` becomes the source of truth
- frames `0..N` are preserved
- frame annotations for `N+1..end` are removed from DynamoDB before tracing resumes
- tracing restarts at frame `N+1`

This keeps the database aligned with the user's visible retrace intent and prevents stale later-frame annotations from surviving a retrace request.
