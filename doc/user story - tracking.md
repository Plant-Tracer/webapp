Here is the simple user story for how a move is uploaded and tracked.

1. User uploads a movie with the **upload** feature. Movie is uploaded as an MP4.
2. User click "analyze." Screen clears and shows the first frame of the movie with the tools for adding and moving trackpoints.
3. User identifies four points: ruler0 and ruler10 (the start and stop points on the ruler), plant1 and plant2 (the two control points on the plant)
4. User clicks "track movie"
5. The JavaScript in analyze.js sends the trackpoints to the server. On the server a loop runs which tracks the points on each frame and producing a new movie.
   The new movie is stored as a derrivative movie. The track points are added as frame-by-frame annotations to the new movie, but we don't store all of the frames
   (we have the medata for each frame)
6. The JavaScript shows the tracked movie, which can be played. (Right now we won't handle what happens if tracking is lost.)
7. If the user doesn't like the tracking, they can click "discard" and all of the trakcpoints and the new movie are abandon.
8. Otherwise, the user can click "save" and the system returns to the list. Now the user sees two movies - the original movie and the tracked movie.
9. 
