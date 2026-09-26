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
2. Browser downloads the untraced MP4 and decodes exact frames with WebCodecs.
3. User browses frames, chooses trim bounds, and places or edits markers.
4. Browser saves explicit edits and the selected trace seeds through Flask.
5. Browser asks lambda-resize to retrace from the edited frame.
6. Browser polls Flask metadata until tracking completes.
7. Browser displays tracked frames, graphs, and CSV download controls.

Navigation marker seeds
~~~~~~~~~~~~~~~~~~~~~~~

An unannotated, untraced frame displays a copy of the latest preceding marker
positions. These display seeds are separate from stored frame annotations;
navigation does not create trackpoints, paths, graph points, or export rows.
Existing destination annotations take precedence, and gaps in traced history
remain empty. Explicitly clearing a frame's markers creates a local seed
boundary, so that frame and subsequent empty frames cannot revive older markers.
Reloaded metadata entries with an explicit empty marker list retain that boundary;
the database records ``empty_marker_annotation`` when a frame is explicitly
cleared. Metadata includes an empty entry for that frame, and trim copying
respects it. Writing nonempty points or resetting tracing removes that boundary.
Ready movies may contain manually placed seeds without having
been traced. Trim controls require multiple loaded frames; a legacy one-frame
view cannot enable trimming solely from its last-tracked-frame metadata.

``MarkerSeedIndex`` builds a nearest-preceding-annotation index in one forward
pass, then resolves each frame in constant lookup time plus the marker-copy
cost. Navigation through an unchanged movie therefore needs O(F) indexing work
for F frames, rather than repeated backward scans. Adding or clearing a frame's
annotations, deleting a marker, resetting tracing, replacing trace results, or
seeding an earlier trim start invalidates the index. Position and name changes
use live annotation objects; replacing the loaded frame array creates a new
index. Explicit edits update local frame data before asynchronous saves return,
so navigation sees the latest placement and older responses cannot revert it.
Moving the trim start backward to an unannotated frame copies the old start's
resolved seeds, including carried positions, and records the new frame index.
Existing destination annotations and explicit empty boundaries take precedence.
Unsaved trim seeds live in ``trim_seed_markers``, separate from ``markers``, so
saved frame ranges, graphs, and paths remain unchanged until an edit or trace.
When the old start has stored annotations, the trim API persists a copy at the
new start, and the browser reflects that saved copy. Edits, reset, trace refresh,
deletion, and renaming also update or clear unsaved trim seeds.
Trim requests wait for pending marker saves before copying the old start, while
retaining the frame selected when the trim control was pressed.

Movie List Flow
---------------

``/list`` is currently rendered as a page that loads movie data from
``POST /api/list-movies`` and builds tables in JavaScript. It separates a
user's published, hidden, deleted, and course-visible movies. This page is
a known candidate for future server-side rendering or a componentized frontend.

Faculty/Admin Flow
------------------

Course admins can list users in their administered courses, bulk-register users,
and hide published movies or unhide hidden course movies. Movie research-use and attribution
choices remain owner-controlled.
