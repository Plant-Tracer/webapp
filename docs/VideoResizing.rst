Resizing Video Files
====================

Why resize my video?
---------------------------

PlantTracer attempts to track the movement of anything in a movie that the user designates with a Marker. It does this by examining the pixels surrounding the marker's position in the next frame and identifying pixels with a similar shape and color nearby. So at one level, the higher the resolution of the video, the more pixels will have to be examined, and the slower the analysis. Since PlantTracer is intended to track the motion of parts of plants, very fine detail is not needed, and indeed a bit of fuzziness is generally beneficial as it tends to smooth out color areas.

Modern digital cameras tend to produce videos with much higher resolution than PlantTracer needs. Standard Definition (480p) is more than enough, and the current iPhone default (1080p) is way more than PlantTracer needs.

PlantTracer puts a limit on the size of the uploaded movies in part to save on storage space and costs, and also to keep down the processing time needed to analyze an image.

One day, we hope that PlantTracer will automatically resize videos upon upload. But until that day, we ask users to make sure their videos are of a size that PlantTracer can easily handle.

PlantTracer video size limits and guidelines
--------------------------------------------

File size: The size of all uploaded video files must be 256 megabytes or less. Files larger than this will be rejected.

Image size: PlantTracer prefers videos in standard definition (480p) and recommends selecting that option when recording or exporting your video. As a general guideline, ensure that the largest dimension of your video is 640 pixels. As an example, a typical 480p video is 640 pixels wide by 480 pixels high. It is important to preserve the aspect ratio of the video when resizing it so that distance calculations remain accurate as items move in both the x and y dimensions of the video.

Movie length and cropping: PlantTracer recommends that movie files have no more than 1000 frames. Some videos have a header or trailer section (often with the recording tool's logo, etc.) that it would be good to crop off prior to uploading, as PlantTracer does not have the ability to crop the movie after uploading. In any case, crop or otherwise edit the movie to remove sections where movement tracking is not intended or desired.

How to Resize a Video
---------------------

Lapse-It
********

`Lapse-It <http://www.lapseit.com/>` is a time-lapse video recording smart phone app that has a free version that produces videos suitable for use with PlantTracer.

Lapse-It free version adds a Lapse-It trailer to each video that needs to be removed prior to uploading and tracking.

Steps to Export a Resized Video Using Lapse-It
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

1. **Open Lapse-It**  
   - Launch the Lapse-It app on your device.

2. **Select the Video**  
   - Choose the recorded time-lapse video you want to export.

3. **Adjust the Resolution**  
   - Tap on **Render**.
   - In the resolution settings, select a preset that ensures neither width nor height exceeds **640 pixels**. If a custom resolution option is available, set the maximum dimension to **640 pixels**.

4. **Export the Video**  
   - Confirm the settings and tap **Render**.
   - Wait for the process to complete, then save or share the exported video.


ffmpeg
******

`ffmpeg <https://www.ffmpeg.org/>` is an open-source command line tool (and library) for image and movie manipulation. ffmpeg is available for Linux, MacOS, and Windows platforms.

Here is a sample command that will resize a video to have at most 640 pixels in either dimension, while maintaining the video's aspect ratio.

.. code-block::

    ffmpeg -i input.mp4 -vf "scale='if(gt(iw,ih),640,-1)':'if(gt(iw,ih),-1,640)'" -c:v libx264 -crf 23 -preset medium -an output.mp4

Explanation
^^^^^^^^^^^

- ``-i input.mp4`` → Specifies the input video file.
- ``-vf "scale='if(gt(iw,ih),640,-1)':'if(gt(iw,ih),-1,640)'"`` → Resizes the video while maintaining aspect ratio:

  - ``iw`` = input width, 
  - ``ih`` = input height.
  - If the width (``iw``) is greater than the height (``ih``), the width is set to **640**, and the height is automatically scaled (``-1``).
  - Otherwise, the height is set to **640**, and the width is automatically scaled (``-1``).

- ``-c:v libx264`` → Uses **H.264** encoding for video.
- ``-crf 23`` → Controls quality (**lower CRF = better quality**, default is **23**).
- ``-preset medium`` → Balances encoding speed and compression.
- ``-an`` → Removes the audio stream.
- ``output.mp4`` → The final resized video.

MacOS
*****

QuickTime Player comes installed by default with MacOS and can be used to trim portions of a video and then export it in set of specified resolutions.

Steps to Resize Video Using QuickTime Player
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

1. **Open QuickTime Player**  
   - Locate your video file and open it with **QuickTime Player**.

2. **Export the Video with a Smaller Resolution**  
   - Click on **File** > **Export As**.
   - Choose a resolution that ensures no dimension exceeds **640 pixels** (e.g., **480p** or manually adjust if available).

3. **Save the Resized Video**  
   - Choose a destination folder.
   - Click **Save**, and QuickTime will process the resized video.

Windows
*******

Windows has a built-in video editor called ClipChamp. Prior to the existence of ClipChamp, there was a program called Video Editor that may be present on Windows 10 systems.

Steps to Resize Video Using Clipchamp
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

1. **Open Clipchamp**  
   - Press ``Win + S`` and search for **Clipchamp**, then open it.

2. **Import the Video**  
   - Click **Create a new video**.
   - Drag and drop your video file into the media library.

3. **Resize the Video**  
   - Click on the video in the timeline.
   - Go to the **Transform** or **Resize** section.
   - Select **"Fit"** to maintain the aspect ratio.
   - Manually adjust the resolution so that neither width nor height exceeds **640 pixels**.

4. **Export the Resized Video**  
   - Click **Export** at the top right.
   - Choose a resolution that ensures no dimension exceeds 640 pixels.
   - Click **Export**, and save your resized video.
