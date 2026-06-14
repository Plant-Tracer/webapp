Web App Theory Of Design
========================

Storage
-------

Plant Tracer always deploys to an existing S3 bucket. The bucket is not created
by the stack and must outlive the stack because it is the long-term archive of
student-uploaded videos.

DynamoDB stores application metadata: users, courses, API keys, movie metadata,
frame trackpoints, and audit logs. Because DynamoDB tables may be rebuilt, any
metadata that must survive with the video, such as research-use and attribution,
is also written into the MP4 file.

Authentication
--------------

Users authenticate with an ``api_key``. API keys are issued per user, stored in
the ``api_keys`` table, and sent to users in login links. Browser pages keep the
active key in the ``api_key`` cookie and expose it to JavaScript as the
``api_key`` global.

Demo mode is separate from normal login. When ``DEMO_MODE`` is set or the host
contains a ``-demo`` label, the server uses the fixed demo API key and hides
mutating UI actions.

Service Boundaries
------------------

* Flask ``flask_app.py`` serves HTML and injects browser globals.
* Flask ``flask_api.py`` serves metadata APIs.
* lambda-resize serves first-frame, playback URL, and retrace APIs.
* S3/MinIO serves movie and ZIP bytes through signed URLs.
* DynamoDB/DynamoDB Local stores structured metadata and trackpoints.

Upload Flow
-----------

1. User opens ``/upload`` through a login link or cookie-authenticated session.
2. Browser validates title, description, file size, research-use, and
   attribution fields.
3. Browser computes the file SHA-256.
4. Browser posts metadata to ``POST /api/new-movie``.
5. Flask creates the movie row and returns a presigned S3 POST for the final
   object key.
6. Browser uploads directly to S3/MinIO.
7. Browser requests the first frame from lambda-resize and links to Analyze.

Analyze Flow
------------

1. Analyze page loads movie metadata from Flask.
2. Frame 0 comes from lambda-resize.
3. User places or edits markers.
4. Browser saves trackpoints through Flask.
5. Browser asks lambda-resize to retrace from the edited frame.
6. Browser polls Flask metadata until tracking completes.
7. Browser displays tracked frames, graphs, and CSV download controls.

Movie List Flow
---------------

``/list`` is currently rendered as a page that loads movie data from
``POST /api/list-movies`` and builds tables in JavaScript. It separates a
user's published, unpublished, deleted, and course-visible movies. This page is
a known candidate for future server-side rendering or a componentized frontend.

Faculty/Admin Flow
------------------

Course admins can list users in their administered courses, bulk-register users,
and publish/unpublish visible course movies. Movie research-use and attribution
choices remain owner-controlled.
