# Optional / Possibly Missing Dict Keys

This note tracks places where plain DynamoDB/API dictionaries can produce
missing-key bugs. It is intentionally line-number-free because these hotspots
move often.

## Current Risk Areas

| Area | Risk | Notes |
|------|------|-------|
| User primary course | High | Upload and page-context code assumes `primary_course_id` exists for logged-in users. Return a clear 400 or setup error before creating movies. |
| Movie access | High | Direct movie access checks must match movie-list visibility: owner, admin, or published course-visible movie. |
| Movie artifact URNs | Medium | `movie_data_urn`, `movie_zipfile_urn`, and `movie_traced_urn` are absent during parts of upload/tracing. Use `.get()` or typed optional fields. |
| Lambda queue messages | Medium | Local/SQS messages are dicts with `api_key`, `movie_id`, and `frame_start`. A Pydantic message model would make retries safer. |
| Boto3 responses | Low | DynamoDB/S3 response shapes are external dict contracts. Use `.get()` for optional fields such as `Items`, `LastEvaluatedKey`, `Errors`, and `Deleted`. |

## Current Model Boundary

`src/app/schema.py` defines Pydantic models for writes and validation:

- `User`
- `Course`
- `ApiKey`
- `Movie`
- `MovieFrame`
- `Trackpoint`
- `LogEntry`

Most read paths still return plain dicts from DynamoDB. That keeps boto3 usage
simple but weakens static checking and encourages repeated string keys.

## Recommended Direction

Short term:

- Keep validating writes with the existing Pydantic models.
- Add targeted `.get()` guards for genuinely optional fields.
- Keep all dict keys in named constants when external APIs force dicts.

Medium term:

- Add Pydantic request/response models for Flask API and Lambda queue payloads.
- Convert high-risk return paths (`get_user`, `get_movie`, movie metadata) to
  typed DTOs or Pydantic models.
- Keep DynamoDB adapter code responsible for converting Decimal and absent
  values into model-friendly Python values.

Long term:

- Make repository/service boundaries return typed models.
- Keep dicts at external boundaries only: Flask form data, JSON bodies, boto3
  requests/responses, and S3 metadata.
