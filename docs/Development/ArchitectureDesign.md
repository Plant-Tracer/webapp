# Architecture Design Principles

Three principles govern where logic lives.

## Frames And Video: lambda-resize

Operations that need full frames or video run in `lambda-resize`.

Current HTTP routes:

- `GET /resize-api/v1/ping`
- `GET /resize-api/v1/first-frame`
- `GET /resize-api/v1/movie-data`
- `POST /resize-api/v1/trace-movie`

The Flask VM does not decode video, extract frames, run tracking, or serve
movie playback bytes. It may create signed S3 upload POST data.

## HTML: flask_app

HTML pages and templates are served by `src/app/flask_app.py`. Routes render
Jinja templates with values from `apikey.page_dict()`, including browser globals
such as `API_BASE`, `LAMBDA_API_BASE`, `api_key`, `user_id`, and `demo_mode`.

## Metadata: flask_api

Movie, user, course, and audit metadata endpoints live in `src/app/flask_api.py`
and use `src/app/odb.py` / `src/app/odb_movie_data.py` for persistence.

Examples:

- `POST /api/new-movie`
- `POST /api/get-movie-metadata`
- `POST /api/put-frame-trackpoints`
- `POST /api/rotate-movie`
- `POST /api/set-metadata`
- `POST /api/list-movies`

Lambda writes DynamoDB metadata only as part of video processing or tracking,
for example setting `status`, `total_frames`, `movie_zipfile_urn`, and
`movie_traced_urn` after tracing.

## Storage Boundary

- S3 stores original movies, traced movies, and ZIP/JPEG artifacts.
- DynamoDB stores users, courses, API keys, movie metadata, frame trackpoints,
  and audit logs.
- The S3 bucket is pre-existing and outlives the CloudFormation stack.
- Research and attribution metadata must also be embedded in the MP4 so the S3
  archive remains self-describing if DynamoDB is rebuilt.

## References

- [Client Lambda API](ClientLambdaAPI.md)
- [Flask API Reference](FlaskAPI.md)
- [DynamoDB](DynamoDB.rst)
- [S3](S3.rst)
- [Movie Metadata](MOVIE_METADATA.rst)
