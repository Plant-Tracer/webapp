# Architecture design principles

Three principles govern where logic lives:

1. **All frames and video processing → lambda-resize**  
   Operations that need full frames or video (get-frame, tracking, rotate-and-zip, start-processing) run only in the Lambda (lambda-resize). The VM (Flask/gunicorn) does not decode video, extract frames, or run tracking.

2. **All HTML → flask_app**  
   All HTML pages and templates are served by the Flask app (`flask_app.py`). There is no other HTTP server serving HTML for the main app.

3. **All metadata → flask_api**  
   Movie and user metadata (get-movie-metadata, put-frame-trackpoints, edit-movie, set-metadata, list movies, etc.) go through the Flask API (`flask_api.py`). The VM owns DynamoDB writes for metadata; Lambda writes metadata only as a result of its own processing (e.g. after rotate-and-zip or tracking).

## Get-movie-data and new-frame on Lambda

**get-movie-data** (GET `/api/v1/movie-data`) returns a 302 redirect to a signed S3 URL for the movie (or zip if `format=zip`). The client uses this URL as the video source (e.g. in `planttracer.js` play button).

**new-frame** (POST `/api/v1` with `action: "new-frame"`) accepts client-supplied frame image data (base64) and writes it to S3 and DynamoDB for a future “create your own timelapse” flow. The VM does not serve this; Lambda handles it for consistency.

## References

- **Client → Lambda:** [ClientLambdaAPI.md](ClientLambdaAPI.md)
- **Processing flow:** [ProcessingPhases.rst](ProcessingPhases.rst)
- **Movie metadata and first frame:** [movie_player.rst](movie_player.rst)
