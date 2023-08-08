# Gallery of Plant Videos
- The webpage would appear as a grid of images. Each thumbnail would be one frame of the video. When clicking on the thumbnail the video would play.

# Purpose
- The gallery would allow user to easily select videos to view. The user would be able to search the database for videos based on various criteria (author, date range).

# Requirements
- access to database with a video as one field of a table
- access to database with thumbnail as one field of a table

# Implementation Plan
- [ ] Implement REST API to get a list of public videos with certain search criteria (date range, keyword, author, etc.). (Returns a cookie for each video)
- [ ] Implement REST API to get metadata for a video (given a cookie)
- [ ] Implement REST API to get an arbitrary frame of a video
- [ ] Implement REST API to download a video assembled from frames.
- [ ] Implement an HTML web page with associated JavaScript that, when loads, gets a list of the videos and displays their names and a frame from the videos.
- [ ] Make the videos play when you click their frame.

# Testing Plan

