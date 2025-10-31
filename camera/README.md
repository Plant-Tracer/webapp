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

- camera.js touches API `/api/v1/camera-start?apikey=<apikey>`
- creates and returns `movie_id`
- each frame is uploaded with `/api/v1/camera-upload-frame?apikey=<apikey>&movie_id=<move_id>`
  - gets an S3 post
  - uploads
- Upload generates an S3 event to add the image to the DynamoDB database.
- When camera finishes, it runs `/api/v1/camera-stop?apikey=<apikey>&movie_id=<movie_id>`
  - causes all frames to be integrated into a single MPEG


Camera code base:
- AWS SAM, modeled on https://github.com/Harvard-CSCI-E-11/spring26/tree/main/etc/e11-cli/lambda-home
- lambda function serves both API endpoints and static pages

- deploy/app/* needs to be vended into app/
