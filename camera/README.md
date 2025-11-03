This directory is for development of the camera.

Ground rules:
- Served entirely from its own lambda
- Camera is completely self-contained. Runs at its own domain (https://app-camera.planttracer.com)
- Communicates with a specific planttracer through hard-coded domain (e.g. `app.planttracer.com`).
- Authenticates with apikey


Camera workflow:

- user goes to `/camera.html` and gets single-page app preloaded with JavaScript
  - /camera.js
  - /camera.css
  - apikey is transmitted as POST.
- If called with GET, present a form asking for apikey (largely for testing).

- camera.js touches API `/api/v1/camera-start`
  - parameters:
    - apikey=<apikey>.
    - frame_start=nnn (starting frame).
    - optional: movie_id (if we are continuing to upload a movie)
  - Returns:
    - `movie_id` for the user's current course with state=UPLOADING
    - signed POSTs for the first N uploads in array of (frame,post parameters)

- each frame is uploaded with the S3 signed post obtained above.
  - gets an signed S3 post
  - uploads
   - JPEG to S3.  JPEG metadata should include the exact time that the picture was taken.

- When camera finishes, it runs `/api/v1/camera-stop?apikey=<apikey>&movie_id=<movie_id>`
  - scans for all frames that were uploade
  - causes a zipfile of all frames to be create and stored.
  - causes all frames to be integrated into a single MPEG

Needed - Data model for movie.
-----------------------------
Each movie has:
 - mp4 of the movie
 - zipfile of the movie's frames (created on demand and persisted until the end of the course)
 - frames database with the trackpoints for each frame (this is not the most efficient approach; the maximum size of a dynamodb record is 400KB. We could store 12,500 elements in it. Can we store this in the movies array?)
 - key frame from movie (first, middle?)


Camera code base:
- AWS SAM, modeled on https://github.com/Harvard-CSCI-E-11/spring26/tree/main/etc/e11-cli/lambda-home
- lambda function serves both API endpoints and static pages

- deploy/app/* needs to be vended into app/
