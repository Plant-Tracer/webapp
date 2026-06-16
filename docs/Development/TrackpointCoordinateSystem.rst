Trackpoint Coordinate System
============================

Purpose
-------

Plant Tracer trackpoints must use a bottom-left coordinate origin in all user-facing
and persisted data. A trackpoint at ``(0, 0)`` is the lower-left corner of the
analysis frame. ``x`` increases to the right and ``y`` increases upward.

The movie image itself is not flipped. Canvas rendering, mouse dragging, and
OpenCV tracking still operate in native image coordinates, where ``(0, 0)`` is
the upper-left corner and ``y`` increases downward.

Coordinate Spaces
-----------------

Plant Tracer uses two coordinate spaces:

``trackpoint`` coordinates
   The persisted and user-visible coordinate system. Origin is the lower-left
   corner of the analysis frame. These values are stored in DynamoDB and
   exported in CSV.

``canvas`` coordinates
   The browser canvas and OpenCV image coordinate system. Origin is the
   upper-left corner of the displayed analysis frame. These values are used only
   for drawing, hit detection, dragging, and optical-flow tracking.

The conversion uses the actual analysis-frame height:

.. code-block:: text

   canvas_x = trackpoint_x
   canvas_y = frame_height - trackpoint_y

   trackpoint_x = canvas_x
   trackpoint_y = frame_height - canvas_y

Coordinates are continuous frame coordinates, not integer pixel indexes. The
top edge of a ``480`` pixel analysis frame has trackpoint ``y = 480``; the bottom
edge has trackpoint ``y = 0``.

Frame Height Source
-------------------

Conversion must use the height of the analysis frame shown to the user, not the
raw uploaded movie height.

The analysis frame is the rotated and scaled frame produced by
``lambda-resize/src/resize_app/mpeg_jpeg_zip.py``. The browser can use the
canvas controller's natural image height once the background frame has loaded.
Lambda tracking can use the current OpenCV frame array height.

DynamoDB Contract
-----------------

The ``movies`` row owns the coordinate-system contract for all trackpoints in
that movie:

.. code-block:: python

   trackpoint_origin: Literal["bottom-left"] | None = None

Rules:

* Missing or ``None`` ``trackpoint_origin`` means legacy ``"top-left"``
  storage. The implementation must not write ``"top-left"`` to new movie rows.
* ``trackpoint_origin = "bottom-left"`` means all stored frame trackpoints for
  that movie use the lower-left-origin contract.
* New movies are created with ``trackpoint_origin = "bottom-left"`` in
  ``odb.create_new_movie()``. ``POST /api/new-movie`` calls this function before
  returning the presigned upload form, and local tooling that creates movies
  should use the same function.
* A movie must not contain mixed-origin frame trackpoints.
* Once a movie's stored frame trackpoints are converted, the movie row is updated
  to ``trackpoint_origin = "bottom-left"``.
* Future trackpoint writes for a ``"bottom-left"`` movie store lower-left-origin
  values directly.

``schema.Movie`` does not currently contain this field. The implementation must
add the field to the Pydantic model and define a named string constant for the
DynamoDB attribute instead of hard-coding the attribute name at each use.

The permanent coordinate contract belongs on the movie row, not on each frame or
trackpoint. Temporary per-frame migration markers are allowed only as internal
rollback/retry machinery during lazy migration; they must not become the public
coordinate contract.

Legacy Migration
----------------

Existing movies without ``trackpoint_origin`` contain top-left-origin
trackpoints. The selected migration strategy is server-side lazy migration of a
complete movie before the first operation that exposes or writes trackpoints
under the new contract.

The lazy migration trigger points are:

* ``POST /api/get-movie-metadata`` when the request returns frame markers.
* ``POST /api/get-movie-trackpoints`` before CSV or JSON export.
* ``POST /api/put-frame-trackpoints`` before accepting edited markers.
* Lambda retracing before reading existing seed trackpoints for optical flow.

Partial migration is not allowed. Saving one edited frame as bottom-left while
other frames remain top-left would corrupt the movie's trackpoint sequence.
Because a movie can have more frame records than DynamoDB can update in one
transaction, lazy migration must not be a naive in-place batch rewrite.

Migration must be resumable or fail closed:

* Determine the analysis-frame height before any write. If it cannot be
  determined, return an error and leave the movie unchanged.
* Serialize migration for a single movie, for example with a conditional
  movie-row migration state or lock.
* Convert frames using an idempotent progress marker or equivalent backup plan
  so a retry never double-flips frames already converted by a failed attempt.
* Set ``trackpoint_origin = "bottom-left"`` only after every frame with
  trackpoints has been converted and verified.
* While a movie is in an incomplete migration state, editing, retracing, and
  exporting trackpoints must wait, retry, or return an error rather than expose
  mixed-origin data.

Browser Responsibilities
------------------------

``canvas_tracer_controller.mjs`` is responsible for translating between stored
trackpoints and canvas objects.

When loading frame markers:

* Read ``metadata.trackpoint_origin`` from the ``metadata`` object returned by
  ``POST /api/get-movie-metadata``.
* For ``"bottom-left"`` movies, convert stored trackpoints to canvas coordinates
  before creating ``Marker`` and ``Line`` objects.
* For legacy ``"top-left"`` movies that have not yet been migrated, use stored
  coordinates as canvas coordinates for visual correctness.

When dragging markers:

* Keep the marker object in canvas coordinates so the marker follows the mouse
  over the unflipped movie.
* The marker table must display converted trackpoint coordinates live while the
  user drags.
* ``get_markers()`` must return trackpoint coordinates, not raw canvas
  coordinates, before posting to ``/api/put-frame-trackpoints``.

The marker table and the posted payload must use the same formatter/conversion
path so initial render, drag updates, saved data, and CSV export agree.

Graph Responsibilities
----------------------

Position graphs should consume trackpoint coordinates. Once frame data is
bottom-left-origin, Y deltas are already positive upward. Chart.js should not
reverse the Y axis to simulate a lower-left origin.

Flask API Responsibilities
--------------------------

``POST /api/put-frame-trackpoints`` receives trackpoint coordinates. For
legacy movies, Flask first runs the lazy migration. For ``"bottom-left"`` movies,
Flask stores those values unchanged.

``POST /api/get-movie-metadata`` returns the movie-row
``trackpoint_origin`` inside ``metadata.trackpoint_origin``. The endpoint already
returns the dictionary from ``odb.get_movie_metadata()`` inside the ``metadata``
response key, so the field is exposed once it exists on ``schema.Movie`` and is
present in the movie row. The field is not in the current schema or response
before this implementation.

When ``POST /api/get-movie-metadata`` returns frame marker coordinates, Flask
first runs the lazy migration if ``metadata.trackpoint_origin`` is missing or
``None``. Returned frame markers therefore use the movie's stored coordinate
contract, which is bottom-left after migration.

``POST /api/get-movie-trackpoints`` first runs the lazy migration and then
exports stored trackpoint values directly. The CSV and JSON exports are
therefore automatically lower-left origin without a separate export-only flip.

Lambda Tracking Responsibilities
--------------------------------

OpenCV must receive canvas/image coordinates. Lambda tracking therefore converts
bottom-left trackpoints to top-left image coordinates before calling optical
flow or drawing labels, then converts tracker output back to bottom-left before
writing frame trackpoints to DynamoDB.

The conversion must use the current processed frame's height:

* before ``cv2.calcOpticalFlowPyrLK``: ``image_y = frame_height - trackpoint_y``
* before ``put_frame_trackpoints``: ``trackpoint_y = frame_height - image_y``

The traced MP4 and frame ZIP are visual artifacts. Marker overlays in those
artifacts are drawn in image coordinates after conversion; the underlying movie
frames are never flipped.

Tests
-----

Substantive tests for the implementation should cover:

* JavaScript marker load: bottom-left stored ``y`` draws at the expected canvas
  ``y``.
* JavaScript drag update: the marker table displays bottom-left ``y`` while the
  marker object remains in canvas coordinates.
* JavaScript save: ``get_markers()`` posts bottom-left coordinates.
* JavaScript path drawing: lines between frames convert both endpoints before
  drawing.
* Graphing: Y deltas use bottom-left values and do not rely on reversed chart
  axes.
* ODB creation: ``odb.create_new_movie()`` stores
  ``trackpoint_origin = "bottom-left"`` for a new movie.
* Flask metadata: ``POST /api/get-movie-metadata`` exposes the movie-row field
  as ``metadata.trackpoint_origin``.
* Flask CSV export: for a bottom-left movie, exported CSV values match stored
  trackpoints.
* Lambda tracking: input bottom-left trackpoints are converted before optical
  flow and converted back before persistence.
* Migration: a legacy top-left movie is converted completely and marked
  ``trackpoint_origin = "bottom-left"``.
* Migration retry: a failed lazy migration cannot double-flip already converted
  frames or expose a mixed-origin movie.

Documentation Follow-up
-----------------------

When the implementation lands, update user-facing coordinate descriptions in
``docs/UserTutorial.rst`` and ``src/app/templates/analyze.html``. Any affected
screenshots under ``docs/tutorial_images/`` should be flagged for user review
rather than replaced automatically.
