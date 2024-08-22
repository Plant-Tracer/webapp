Here is the simple user story for how a movie is uploaded and tracked.

User Story
==========

#. User uploads a movie with the (existing) **upload** feature. Movie is uploaded as an MP4.  IMPLEMENTED

   - [ ]  If the user uploads a quicktime, convert it to an MP4 with ffpmeg: https://superuser.com/questions/1155186/convert-mov-video-to-mp4-with-ffmpeg.

#. User clicks "analyze" on the movie list.  IMPLEMENTED

   * Screen clears and shows the first frame of the movie with the tools for adding and moving trackpoints.

   - [ ] `frame_start` is set to 0.
   - [ ] A text field with the frame number is shown.
   - [ ] A new button `goto frame N` is available.  We use frame number.
   - [ ] Requires update to get-frame API that gets frame N from the movie
   - [ ] Requires update to get-frame implementation to use Quicktime API to stream through the movie and choose the Nth frame.

#. User identifies four points:

   * ruler0  - the origin of the calibration ruler.
   * rulerNN - the location of milimeter NN on the ruler. (e.g. ruler10 for the 10mm/1cm mark)
   * plant1  - a control point on the plant being monitored
   * plant2  - Another control point on the plant being monitored.

     - [ ] The above message is displayed as a help message in the analysis pane. The message is specified in the file analysis.js.

#. User clicks "track movie"

   - [ ] `analyze.js` sends the trackpoints to the server with the `/api/put-frame-analysis` API call.
   - [ ] `analyze.js` displays `tracking...` to the user.
   - [ ] `analyze.js` runs the API call `/api/track-movie` which initiates server-side tracking from frame n=0.

     * :param: api_key
     * :param: movie_id
     * :param: frame_start (frame number)  (trackpoints for this frame must be in the database)
     * Possible return codes:

       - [ ] error True - Message - Only two ruler trackpoints may be specified
       - [ ] error True - Message - No plant trackpoints detected
       - [ ] error False - Plant tracked. `analyze.js` proceeds to step 6.

#. The `track-movie` API call did the following:

   - [ ]  Runs `tracker.track_movie_from_db` which:

     - [ ] Creates a temporary file on the server file system for the movie (because OpenCV will not track from memory)
     - [ ] Copies frames 0..(N-1) original movie to output file, rendering the points and the frame number with what's already in the database.
     - [ ] Tracks from frames N to the end, starting with the provided trackpoints.
     - [ ] The tracked points are written into the database table `movie_frame_trackpoints` for each frame.
     - In both cases, rendering includes the points and the frame number.
     - [ ] Write the new rendered tracked movie to the database with the title `{old-title} TRACKED`
     - [ ] If a previous 'tracked movie' is in the database, delete it.
     - [ ] Return OK to caller.

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
====

#. Do we want to use frame numbers, or always use msec?

   - frame number and msec are easy to calculate from each other, assuming a constant frame rate.
   - If the frame rate is not constant, we need both.
   - The original database of frames was to support frame uploading, not frame access.
   - If we don't know the movie rate, then we only have frame number. So frame number should always be supported.

#. Do we want to use movie time, or real time?
   - We always use movie time, since we might not know real-time.

#. If we are using real time, how do we get the scaling factor?

Agenda
======

- [ ] Implement /api/track-movie
- [ ] Remove tracking code from get-frame and implement get-frame N code.
- [ ] Implement updates to analyze.js for frame 0
- [ ] Implement updates to analyze.js for frame N
- [ ] Implement download of CSV file
