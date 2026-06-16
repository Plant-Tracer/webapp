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

   trackpoint_origin: Literal["top-left", "bottom-left"] = "top-left"

Rules:

* Missing ``trackpoint_origin`` means legacy ``"top-left"`` storage.
* New movies are created with ``trackpoint_origin = "bottom-left"``.
* A movie must not contain mixed-origin frame trackpoints.
* Once a movie's stored frame trackpoints are converted, the movie row is updated
  to ``trackpoint_origin = "bottom-left"``.
* Future trackpoint writes for a ``"bottom-left"`` movie store lower-left-origin
  values directly.

The field belongs on the movie row, not on each frame or trackpoint. Per-frame
or per-trackpoint origin would create mixed-origin data and unnecessary DynamoDB
payload growth.

Legacy Migration
----------------

Existing movies without ``trackpoint_origin`` contain top-left-origin
trackpoints. The implementation must choose one of these migration paths before
allowing new bottom-left writes to those movies:

* Run a one-time DynamoDB migration that converts every stored trackpoint using
  the analysis-frame height and then sets ``trackpoint_origin`` to
  ``"bottom-left"``.
* Lazily migrate a complete movie before its first edit, retrace, or CSV export
  under the new coordinate contract.

Partial migration is not allowed. Saving one edited frame as bottom-left while
other frames remain top-left would corrupt the movie's trackpoint sequence.

Browser Responsibilities
------------------------

``canvas_tracer_controller.mjs`` is responsible for translating between stored
trackpoints and canvas objects.

When loading frame markers:

* Read ``metadata.trackpoint_origin``.
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
``"bottom-left"`` movies, Flask stores those values unchanged.

``POST /api/get-movie-metadata`` returns frame marker coordinates in the movie's
stored coordinate contract. For fully migrated movies this means bottom-left
trackpoint coordinates.

``POST /api/get-movie-trackpoints`` exports stored trackpoint values directly.
For ``"bottom-left"`` movies, the CSV is therefore automatically lower-left
origin without a separate CSV-only flip.

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
* Flask CSV export: for a bottom-left movie, exported CSV values match stored
  trackpoints.
* Lambda tracking: input bottom-left trackpoints are converted before optical
  flow and converted back before persistence.
* Migration: a legacy top-left movie is converted completely and marked
  ``trackpoint_origin = "bottom-left"``.

Documentation Follow-up
-----------------------

When the implementation lands, update user-facing coordinate descriptions in
``docs/UserTutorial.rst`` and ``src/app/templates/analyze.html``. Any affected
screenshots under ``docs/tutorial_images/`` should be flagged for user review
rather than replaced automatically.
