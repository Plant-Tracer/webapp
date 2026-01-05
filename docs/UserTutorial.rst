Plant Tracer Web App Tutorial
=============================

Welcome and Registration
-------------------------
- Go to `app.planttracer.com/register`.
- Register for an account using your Name, Email Address, and Course Key.
- If you are using Plant Tracer with a specific course or project, you can enter your course Keyey provided by your instructor or project leader.
- Alternately, you can register for the Web course whose course key is 389f-4163

.. image:: tutorial_images/register.png
   :alt: Plant Tracer Registration

- Look for an email from `admin@planttracer.com`. Click on the second link to view movies. The first link will allow you to upload movies.

.. image:: tutorial_images/admin_email_link.png
    :alt: email from Plant Tracer

Viewing movies
--------------
- The second link in the email will bring you to the Welcome page.
- Click on "Movies" in the menu bar at the top of the page to see a list of movies to analyze.

.. image:: tutorial_images/welcome_page.png
   :alt: Selecting a sample movie on Plant Tracer

- Click on the analyze button to see the tracked movie.

.. image:: tutorial_images/choose_analyze.png
   :alt: Selecting a sample movie on Plant Tracer

Uploading Movies (optional)
---------------------------
- Ensure that your video is of a size that works well with PlantTracer. You may have to resize it before uploading. The movement tracking algorithm(s) PlantTracer use(s) actually work better with fairly low resolution, so no need to be concerned about losing any detail. We recommend a frame size of no more than 640 pixels in either dimension. We recommend a maxiumum of 1000 frames per movie. Your movie file must be 256MB or less or you won't be able to upload it all. Eventually, PlantTracer will automatically resize (downsample) uploaded movies, but for now, the user must do this prior to upload. See :doc:`VideoResizing` for some ways to resize videos.
- PlantTracer will accept videos in most well-known video file formats, but MP4 is probably best.
- To upload your movie, select Upload from the menu bar at the top of the browser frame.
- Enter the title of the file and a description of the movie.
- Choose a file to upload.

.. image:: tutorial_images/upload_movie.png
   :alt: Uploading Movies on Plant Tracer

Tracking the Uploaded Movie
---------------------------
- Once the file is uploaded, you can choose to track it.
- In the bottom left of the page, click on the button labeled "Track the uploaded movie".

.. image:: tutorial_images/track_uploaded_movie.png
   :alt: Tracking uploaded movie on Plant Tracer

- PlantTracer places three markers on newly uploaded movies automatically. They initially appear on the left side of the movie frame. These also appear in the Marker Table to the right (or beneath) the video frame.
- PlantTracer will attempt to track the motion of whatever part of the image a marker is placed over, frame by frame.
- It is the user's job to position the markers appropriately. To move a marker, click on it, and drag it to the desired location.
- You may use the Marker Table to add and delete markers whose names have meaning for your motion analysis. There may be any number of markers. Markers may not be renamed, so if you want to rename a marker, delete it and add another with the name you want.
- PlantTracer will attempt to track the motion related to every marker.
- Typically, the apex of some part of the plant is tracked. So, to do that, move the Apex marker, for example, to the top of the vertical stem.
- Marker that have names of the form RulerXXmm are special. XX is any non-negative integer. These markers are intended to be used for distance calibration. Using the default Ruler markers, if the image has a ruler in it, move the Ruler0mm marker to the beginning of the ruler in the image, and move the Ruler10mm marker to the 10mm mark on the ruler. In this way, PlantTracer can report analysis results in millimeters rather than numbers of pixels in the image.
- There can be any number of RulerXXmm markers, but PlantTracer will only use the RulerXXmm markers with the lowest and highest XX values in its calculations, and ignores any intermediate RulerXXmm markers for purposes of distance calculations. PlantTracer only uses mm distances.
- If there are fewer than two RulerXXmm markers on a given analysis, then analysis results are calclulated and presented using units of pixels.

.. image:: tutorial_images/moving_marker.png
   :alt: Tracking uploaded movie on Plant Tracer

- The Apex marker, and ruler markers need to be moved to the appropriate location.

.. image:: tutorial_images/placed_markers.png
   :alt: Tracking uploaded movie on Plant Tracer

Viewing the trace of a Movie
----------------------------
- Once the tracked movie has loaded you will see the image of the first frame, the data table and the graphs of the movement.

.. image:: tutorial_images/analyzed_movie.png
   :alt: Viewing the tracked movie, data and graphs on Plant Tracer

- Click on the play button to view the movement of the apex in all frames of the movie.

.. image:: tutorial_images/play_button.png
   :alt: Viewing the traced movie on Plant Tracer

Interpreting and Reading Results
--------------------------------
- Use the arrow buttons just below the tracked movie to play, or navigate to a particular frame.
- Graphs help visualize the horizontal (x position) and vertical (y position).
- When you are satisfied with the tracking, you can press the button "Download Trackpoints".
- At this point, you are ready to use a spreadsheet to analyze and graph the data.

.. image:: tutorial_images/download_trackpoints.png
   :alt: Reading Results in Plant Tracer

Further Adjustments to Tracking
-------------------------------
- You can enlarge the image of the movie to better view the markers and tracing.

.. image:: tutorial_images/movie_size_adjustment.png
   :alt: Adjusting the Zoom in Plant Tracer

- You have the option of re-tracking the movie from that frame.

.. image:: tutorial_images/fall_off_apex.png
   :alt: Other Adjustments in Plant Tracer

- Use the arrow buttons just below the original movie to navigate to the frame where tracking was lost.
- Then move the apex marker to the correct position. Now press the button "re-track movie".

.. image:: tutorial_images/retrack_movie.png
   :alt: Retrack Movie in Plant Tracer

Converting Frames to Time
-------------------------

Currently, the Plant Tracer webapp tracks time only as frame numbers in the uploaded movie file. It is up to the the user to convert frames to elapsed timestamps from the beginning of the video. When recording the movie, the frame period was set: you must know what that was. In Lapse-It, this is one of the parameters set for the recording. Typically, the frame period is one frame every two minutes (120 seconds) or 30 frames per hour.

To convert frame numbers to time, multiply the frame number by the frame period:

- t[n] = n * FP

For example if the period FP = 2 minutes, then:

- t[0] = 0 * 2 minutes = 0 minutes
- t[1] = 1 * 2 minutes = 2 minutes
- t[2] = 2 * 2 minutes = 4 minutes
- etc.

If you have a frame rate (frames per unit of time) rather than a frame period, the frame rate is just the inverse of the period. If the frame period is 2 seconds, the frame rate is 1 frame/2 seconds or 0.5 frames/second.

Let FR be the frame rate. The time t[n] at frame[n] is therefore (N * (1/FR)).

For example, if FR = 0.5, then:

- t[0] = 0 * 1/0.5 = 0 seconds
- t[1] = 1 * 1/0.5 = 2 seconds
- t[2] = 2 * 1/0.5 = 4 seconds
- etc.