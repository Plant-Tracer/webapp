Upload and Track User Story
===========================

Here is the simple user story for how a movie is uploaded and tracked.

User Story
----------

#. User uploads a movie with the (existing) **upload** feature. Movie is uploaded as an MP4.  IMPLEMENTED

   - [ ]  If the user uploads a quicktime, convert it to an MP4 with ffpmeg: https://superuser.com/questions/1155186/convert-mov-video-to-mp4-with-ffmpeg.

#. User clicks "analyze" on the movie list.  IMPLEMENTED

   * Screen clears and shows the first frame of the movie with the tools for adding and moving trackpoints.

   - [ ] `frame_start` is set to 0.
   - [ ] A text field with the frame number is shown.
   - [ ] A new button `goto frame N` is available.  We use frame number.
   - [ ] get-frame (Lambda GET api/v1/frame) returns frame N from the movie; no VM frame extraction.

#. User identifies four points:

   * ruler0  - the origin of the calibration ruler.
   * rulerNN - the location of milimeter NN on the ruler. (e.g. ruler10 for the 10mm/1cm mark)
   * plant1  - a control point on the plant being monitored
   * plant2  - Another control point on the plant being monitored.

     - [ ] The above message is displayed as a help message in the analysis pane. The message is specified in the file analysis.js.

#. User clicks "track movie"

   - [ ] `analyze.js` sends the trackpoints to the server with the `/api/put-frame-analysis` API call.
   - [ ] `analyze.js` displays `tracking...` to the user.
   - [ ] The client requests tracking via the **Lambda API** (POST ``api/v1`` with ``action=track-movie``, ``api_key``, ``movie_id``, ``frame_start``). Tracking runs in lambda-resize only.

     * :param: api_key
     * :param: movie_id
     * :param: frame_start (frame number)  (trackpoints for this frame must be in the database)
     * Possible return codes:

       - [ ] error True - Message - Only two ruler trackpoints may be specified
       - [ ] error True - Message - No plant trackpoints detected
       - [ ] error False - Plant tracked. `analyze.js` proceeds to step 6.

#. The track-movie request (Lambda API) does the following (in **lambda-resize**, not on the VM):

    - [ ]  Lambda runs the tracking pipeline which:

     - [ ] Reads the movie from S3, applies rotation if needed, and runs optical-flow tracking from the given frame.
     - [ ] Writes trackpoints to DynamoDB per frame and builds the frame zip. The tracker owns the zip archive: for later batches it reads the existing zip from S3, copies the old JPEGs into a new temporary zip, appends the new batch frames, and then writes the updated zip back to S3 and sets ``movie_zipfile_urn`` and metadata (width, height, fps, total_frames, etc.) in DynamoDB.
     - [ ] The VM (Flask) does not run tracking; the client calls the Lambda API and then polls ``get-movie-metadata`` until tracking is complete.

#. When the tracking is done:

   - [ ] the `tracking...` is replaced with `movie tracked`
   - [ ] The tracked movie appears underneath the original movie (UX principle: don't make unexpected changes)
   - [ ] A play button appears for the new movie.

#. If the user notices that the tracking diverges from the video, they will be able to retrack from frame NN.

   - [ ] A text field 'frame #' is present.
   - [ ] A button `analyze from frame #` is present.
   - [ ] Clicking the button reloads the tracking system but starting with frame `frame_start`

#. When the user is done, the user can click 'return to list' and go back to the list. (There is no save button.)

#. Now the user sees two movies - the original movie and the tracked movie.

#. There is also a download button which downloads all of the trackpoints from the database as a CSV.

   - [ ] Implement a download button.
   - [ ] The students will have to do the triangle math to turn the two ruler points and the tracked point into an (x,y) on a mm scale. This requires high school trig.

Note
----

#. Do we want to use frame numbers, or always use msec?

   - frame number and msec are easy to calculate from each other, assuming a constant frame rate.
   - If the frame rate is not constant, we need both.
   - The original database of frames was to support frame uploading, not frame access.
   - If we don't know the movie rate, then we only have frame number. So frame number should always be supported.

#. Do we want to use movie time, or real time?
   - We always use movie time, since we might not know real-time.

#. If we are using real time, how do we get the scaling factor?

Agenda
------

- [x] Tracking: client calls Lambda API (POST api/v1 action=track-movie). get-frame is in lambda-resize (GET api/v1/frame).
- [ ] Implement updates to analyze.js for frame 0
- [ ] Implement updates to analyze.js for frame N
- [ ] Implement download of CSV file
