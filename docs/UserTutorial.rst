Plant Tracer Web App Tutorial
=============================

Welcome and Registration
-------------------------

- If this is your first time using Plant Tracer, you will need to register for an account, unless your course administrator has registered an account for you in advance. To register:

- Go to `prod.planttracer.com/register`.
- Register for an account using your Name, Email Address, and Course Key.
- If you are using Plant Tracer with a specific course or project, you can enter your course Key provided by your course administrator (your instructor should be able to help you here).
- Alternately, you can register for the Web course whose course key is 2c01-48cd

.. image:: tutorial_images/register.png
   :alt: Plant Tracer registration form with Name, Email Address, and Course Key input fields and a Register button

- Once you are registered, look for an email from `admin@planttracer.com`. Click the **Log in to Plant Tracer** button to log in. From there you can upload movies or view a list of existing movies to work with.

.. image:: tutorial_images/admin_email_link.png
    :alt: Plant Tracer login email highlighting the Log in to Plant Tracer button

Viewing movies
--------------
- Click on "Movies" in the menu bar at the top of the page to see a list of movies to analyze.

.. image:: tutorial_images/welcome_page.png
   :alt: Plant Tracer Movies page listing available movies with title, description, and Analyze buttons

- Click on the analyze button to see the tracked movie.

.. image:: tutorial_images/choose_analyze.png
   :alt: Close-up of the Plant Tracer movie list showing the Analyze button for a movie

Uploading Movies (optional)
---------------------------
- Ensure that your video is of a size that works well with Plant Tracer. You may have to resize it before uploading, either by trimming its length or reducing its resolution. The movement tracking algorithm(s) Plant Tracer use(s) actually work better with fairly low resolution, so no need to be concerned about losing any detail. We recommend a frame size of no more than 640 pixels in either dimension. We recommend a maxiumum of 1,000 frames per movie, though we permit a maximum of 10,000 frames. Your movie file must be 256MB or less or you won't be able to upload it all. Plant Tracer will automatically resize (downsample) uploaded movies to a width of 640 pixels, if the movies have a resolution higher than that. See :doc:`VideoResizing` for some ways to resize videos.
- Plant Tracer will accept videos in most well-known video file formats, but MP4 is probably best.
- To upload your movie, select Upload from the menu bar at the top of the browser frame.
- Enter the title of the file and a description of the movie.
- If you would like to permit your uploaded movie to be used in academic research, check the box "The uploaded movie may be used in academic research." You will then be asked whether you want to be credited for this contribution and what name you want to be credited with.
- Choose a file to upload.

.. image:: tutorial_images/upload_movie.png
   :alt: Plant Tracer Upload page with fields for movie title, description, research consent checkbox, and file chooser

Tracking the Uploaded Movie
---------------------------
- Once the file is uploaded, the page shows a first frame of your movie and a "Next steps" section. Click **Analyze** to go to the Analyze page. (The **Track the uploaded movie** link goes to the same place.)
- There's an opportunity to rotate the movie 90° clockwise as many times as necessary to orient the movie properly if it's not. Note that once you proceed to the Analyze page, you won't be able to rotate the movie anymore.

.. image:: tutorial_images/track_uploaded_movie.png
   :alt: Post-upload confirmation page showing the movie's first frame and a Next Steps section with Analyze and Track the uploaded movie links

- On the Analyze page, position the markers (described below), then click **Trace movie** to begin tracking.
- Plant Tracer places three markers on newly uploaded movies automatically. They initially appear on the left side of the movie frame. These also appear in the Marker Table to the right (or beneath) the video frame.
- Plant Tracer will attempt to track the motion of whatever part of the image a marker is placed over, frame by frame.
- It is the user's job to position the markers appropriately. To move a marker, click on it, and drag it to the desired location.
- You may use the Marker Table to add and delete markers whose names have meaning for your motion analysis. There may be any number of markers. Markers may not be renamed, so if you want to rename a marker, delete it and add another with the name you want.
- Plant Tracer will attempt to track the motion related to every marker.
- Typically, the apex of some part of the plant is tracked. So, to do that, move the Apex marker, for example, to the top of the vertical stem.
- Marker that have names of the form RulerXXmm are special. XX is any non-negative integer. These markers are intended to be used for distance calibration. Using the default Ruler markers, if the image has a ruler in it, move the Ruler0mm marker to the beginning of the ruler in the image, and move the Ruler10mm marker to the 10mm mark on the ruler. In this way, Plant Tracer can report analysis results in millimeters rather than numbers of pixels in the image.
- There can be any number of RulerXXmm markers, but Plant Tracer will only use the RulerXXmm markers with the lowest and highest XX values in its calculations, and ignores any intermediate RulerXXmm markers for purposes of distance calculations. Plant Tracer only uses mm distances.
- If there are fewer than two RulerXXmm markers on a given analysis, then analysis results are calclulated and presented using units of pixels.

.. image:: tutorial_images/moving_marker.png
   :alt: Plant Tracer Analyze page showing three markers stacked at the left edge of the frame in their initial positions, with a Trace movie button

- The Apex and ruler markers need to be moved to the appropriate location.

.. image:: tutorial_images/placed_markers.png
   :alt: Plant Tracer Analyze page with the Apex marker positioned at the top of the plant stem and ruler markers placed along a ruler in the frame

Viewing the trace of a Movie
----------------------------
- Once the tracked movie has loaded you will see the image of the first frame, the marker table and graphs of the tracked movement.

.. image:: tutorial_images/analyzed_movie.png
   :alt: Plant Tracer Analyze page showing the tracked movie at frame 0, a marker position table, and x and y position graphs

- Click on the play button to view the movement of the apex in all frames of the movie.

Interpreting and Reading Results
--------------------------------
- Use the arrow buttons just below the tracked movie to play, or navigate to a particular frame.
- The Position Graphs visualize the change in the non-RulerXX markers'horizontal (x position) and vertical (y position) since frame 0.
- When tracking is complete, you can press the "Download Trackpoints" button to get the tracking data in CSV format.
- At this point, you are ready to use a spreadsheet to further analyze and graph the data.

.. image:: tutorial_images/download_trackpoints.png
   :alt: Plant Tracer results page showing the tracked movie, data table, and a Download Trackpoints button for exporting tracking data as CSV

Further Adjustments to Tracking
-------------------------------
- You can enlarge the image of the movie to better view the markers and tracing.

.. image:: tutorial_images/movie_size_adjustment.png
   :alt: Plant Tracer movie size controls showing a zoom dropdown for enlarging the movie display

- You have the option of re-tracking the movie from that frame.

.. image:: tutorial_images/fall_off_apex.png
   :alt: Plant Tracer Analyze page showing the Apex marker drifted away from the plant tip at a later frame, indicating lost tracking

- Use the arrow buttons just below the original movie to navigate to the frame where tracking was lost.
- Then move the apex marker to the correct position. Now press the button "re-track movie".

.. image:: tutorial_images/retrack_movie.png
   :alt: Plant Tracer Analyze page with the Apex marker manually repositioned on the plant tip and a Retrace movie button to restart tracking from this frame

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

Let FR be the frame rate. The time t[n] at frame[n] is therefore (n * (1/FR)).

For example, if FR = 0.5, then:

- t[0] = 0 * 1/0.5 = 0 seconds
- t[1] = 1 * 1/0.5 = 2 seconds
- t[2] = 2 * 1/0.5 = 4 seconds
- etc.