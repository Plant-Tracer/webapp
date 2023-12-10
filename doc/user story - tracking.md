Here is the simple user story for how a movie is uploaded and tracked.

1. User uploads a movie with the **upload** feature. Movie is uploaded as an MP4.
2. User clicks "analyze" on the movie list.
   * Screen clears and shows the first frame of the movie with the tools for adding and moving trackpoints.
3. User identifies four points:
   * ruler0  - the origin of the calibration ruler.
   * rulerNN - the location of milimeter NN on the ruler. (e.g. ruler10 for the 10mm/1cm mark)
   * plant1  - a control point on the plant being monitored
   * plant2  - Another control point on the plant being monitored.
4. User clicks "track movie"
   * `analyze.js` sends the trackpoints to the server with the `/api/put-frame-analysis` API call.
   * `analyze.js` displays `tracking...` to the user.
   * `analyze.js` runs the API call `/api/track-movie` which initiates server-side tracking from frame n=0.
     - :param: api_key
     - :param: movie_id
     - :param: frame_start (frame number)  (trackpoints for this frame must be in the databse)
     - :param:
5. The `track-movie` API call does the following:
   * Runs `tracker.track_movie_from_db` which:
     - Creates a temporary file on the server file system for the movie.
     - Copies frames 0..(N-1) original movie to output file, rendering the points and the frame number with what's already in the database.
     - Tracks from frames N to the end, starting with the provided trackpoints.The tracked points are written into the database for each frame.
     - In both cases, rendering includes the points and the frame number.
     - Write the new rendered tracked movie to the database
     - If a previous 'tracked movie' is in the database, delete it.
     - Return OK to caller.
6. When the tracking is done, the `tracking...` is replaced with `movie tracked` and offers the ability to play the tracked movie.
7. If the user notices that the tracking diverges from the video, they will be able to retrack from frame NN.
8. When the user is done, the user can click 'return to list' and go back to the list.  (There is no save button.)
9. Now the user sees two movies - the original movie and the tracked movie.
10. There is also a download button which downloads all of the trackpoints from the database as a CSV. The students will have to do the triangel math to turn the two ruler points and the tracked point into an (x,y) on a mm scale. This requires high school trig.
