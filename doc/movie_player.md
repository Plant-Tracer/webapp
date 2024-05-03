Design of the movie player:

API calls on that the JavaScript movie player can use
=====================================================
- get-frame - returns the frame as JPEG
  Gets an individual frame. Returns a JPEG of the frame that is
  fetched from S3 (if the frame is available) or from the movie (by
  single-framing through the movie if the frame is not available).

  If it has to single frame through the movie, it saves the frame.

- edit-movie
  If movie is rotated, all of the frames and trackpoints have to be
  deleted. This should be done automatically on the server.

- get-movie-metadata
  Gets information about individual frames. Parameters:
  frame_start - starting frame to get;
  frame_count - count of frames to get; 0 for no frames
  what - comma-delimited string - 'trackpoints', 'annotations', 'urls'

  Returns JSON dictionary:
  ['metadata'] - movie metadata (same as get-metadata)
  ['frames'] - annotations, trackpoints, or URLS.
  ['frames']['10']      (where '10' is a frame number) - per-frame dictionary.
  ['frames']['10']['trackpoints'] - array of the trackpoints for that frame
  ['frames']['10']['annotations'] - array of the annotations for that frame
  ['frames']['10']['url'] - signed URL for the frame, from S3

Client Side
===========

Tunable Constants
-----------------
FRAME_BATCH_SIZE - number of frames that get loaded at once
FRAME_LOW_WATER_MARK - When this close to last

State Variables
----------------
api_key - user's API key
movie_id - movie being tracked
total_frames - Total number of frames, which go from from 0 to (total_frames-1)
last_tracked_frame - last frame that was tracked. Typically 0 or total_frames-1. (Frame 0 is manually tracked.)
current_frame  - current frame of movie displayed
tracking - true if server is currently tracking frames and player is waiting for tracking to be done.
playing - true if player is currently playing a movie.
frames[] - dictionary that matches what was returned above
  'url' is the URL to load for the frame
  'jpeg' is a JPEG for the frame, or null if it hasn't loaded yet.
fps - frames for per second for playback

Class Hiearchy
--------------
CanvasController.
* native (w,h)
* zoomed (w,h) (the <canvas> is actually resized.)
* future: put in a scroller.
* HTML objects it owns:
  - <canvas> where things get drawn
 * <div> where canvas marker inventory is displayed
 * zoom pull-down
* Functions:
  * display list with draggable objects.
  * Zoom with objects that can be zoomable or not zoomable
  * Button to create new objects

CanvasItem - root class for things that goes on the CanvasController:
* (x,y) (w,h) rectangle
* draw method (in canvas coordinates; zooming is invisible to items.)
* Hit detection

MarkerItem(CanvasItem)- Markers/Trackpoints
ImageItem(CanvasItem) - draws an image (does not load it.)

MovieController
* Subclass of CanvasController.
* Loaded with URLs of every frame.
* Outlets for movement buttons:
  - Forward
  - Backward
  - Play
  - Start
  - Jump Forward 10 sec
  - Jump Backward 10 sec
  - Frame counter
* Implements load logic.


TrackerController
* Owns a Canvas Controller (not a subclass of it)
* Callback when Trackers are moved
* On end of drag, sends new trackpoints to server - but this does not retrack the movie or delete other trackpoints.

Invariants:
* (playing == false && tracking == false) or (playing==true and tracking==false) or (tracking==true and playing==false)
* 0 <= last_tracked_frame < total_frames
* total_frames > 0
* 0 <= current_frame < total_frames

User Stories
------------
Initial Page Loads:
* MoviePlayer gets first frame and trackpoints to display (give user immediate freedback).
* MoviePlayer requests background load of first FRAME_BATCH_SIZE frames.

Movie playing:
* When player gets to LAST_FRAME_LOADED-BUFFER, it requests the next N frames. (with an async load request.)
* If we get to frame N and frame N+1 isn't loaded, we do a request to load just it and a request to do the next FRAME_BATCH_SIZE.
* checkbox to 'show trails' which causes track trails to be display from 0..current_frame


Moving track points:
* Whenever a track point is moved, the 'retrack from here to end' is displayed.
* When 'track from here' button is clicked, all other buttons are disabled until track  ing is finished.


When tracking:
* All buttons are disabled.
* Track status displays. When the last frame is tracked, buttons are re-enabled.

Download buttons:
* Original movie
* Tracked movie (Do we need this?)
* GIF showing the tracking (https://stackoverflow.com/questions/753190/programmatically-generate-video-or-animated-gif-in-python)
* Download trackpoints
