Here is the simple user story for how a movie is uploaded and tracked.

1. User uploads a movie with the (existing) **upload** feature. Movie is uploaded as an MP4.  IMPLEMENTED
   - [ ]  If the user uploads a quicktime, convert it to an MP4 with ffpmeg: https://superuser.com/questions/1155186/convert-mov-video-to-mp4-with-ffmpeg.
2. User clicks "analyze" on the movie list.  IMPLEMENTED
   * Screen clears and shows the first frame of the movie with the tools for adding and moving trackpoints.
   - [ ] `frame_start` is set to 0.
   - [ ] A text field with the frame number is shown.
   - [ ] A new button `goto frame N` is available.
   - [ ] Requires update to get-frame API that gets frame N from the movie
   - [ ] Requires update to get-frame implementation to use Quicktime API to stream through the movie and choose the Nth frame.
3. User identifies four points:
   * ruler0  - the origin of the calibration ruler.
   * rulerNN - the location of milimeter NN on the ruler. (e.g. ruler10 for the 10mm/1cm mark)
   * plant1  - a control point on the plant being monitored
   * plant2  - Another control point on the plant being monitored.
   - [ ] The above message is displayed as a help message in the analysis pane. The message is specified in the file analysis.js.
4. User clicks "track movie"
   - [ ] `analyze.js` sends the trackpoints to the server with the `/api/put-frame-analysis` API call.
   - [ ] `analyze.js` displays `tracking...` to the user.
   - [ ] `analyze.js` runs the API call `/api/track-movie` which initiates server-side tracking from frame n=0.
     - :param: api_key
     - :param: movie_id
     - :param: frame_start (frame number)  (trackpoints for this frame must be in the databse)
     - Possible return codes:
       - [ ] error True - Message - Only two ruler trackpoints may be specified
       - [ ] error True - Message - No plant trackpoints detected
       - [ ] error False - Plant tracked. `analyze.js` proceeds to step 6.
5. The `track-movie` API call did the following:
   - [ ]  Runs `tracker.track_movie_from_db` which:
     - [ ] Creates a temporary file on the server file system for the movie (because OpenCV will not track from memory)
     - [ ] Copies frames 0..(N-1) original movie to output file, rendering the points and the frame number with what's already in the database.
     - [ ] Tracks from frames N to the end, starting with the provided trackpoints.
     - [ ] The tracked points are written into the database table `movie_frame_trackpoints` for each frame.
     - In both cases, rendering includes the points and the frame number.
     - [ ] Write the new rendered tracked movie to the database with the title `{old-title} TRACKED`
     - [ ] If a previous 'tracked movie' is in the database, delete it.
     - [ ] Return OK to caller.
6. When the tracking is done:
   - [ ] the `tracking...` is replaced with `movie tracked`
   - [ ] The tracked movie appears underneath the original movie (UX principle: don't make unexpectec changes)
   - [ ] A play button appears for the new movie.
7. If the user notices that the tracking diverges from the video, they will be able to retrack from frame NN.
   - [ ] A text field 'frame #' is present.
   - [ ] A button `anayze from frame #` is present.
   - [ ] Clicking the button reloads the tracking system but starting with frame `frame_start`
8. When the user is done, the user can click 'return to list' and go back to the list.  (There is no save button.)
9. Now the user sees two movies - the original movie and the tracked movie.
10. There is also a download button which downloads all of the trackpoints from the database as a CSV. The students will have to do the triangel math to turn the two ruler points and the tracked point into an (x,y) on a mm scale. This requires high school trig.


Questions to be decided by team:

1. Do we want to use frame numbers, or always use msec?
2. Do we want to use movie time, or real time?
3. If we are using real time, how do we get the scaling factor?
