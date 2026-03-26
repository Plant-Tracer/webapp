This directory is for lambda-resize

Environment variables that you should know about/set:

Core Functionality
=================
Lambda-resize performs the following functions:

* Listens on AWS HTTP API for the following commands:
  - `GET /resize-api/v1/ping` - health check
  - `GET /resize-api/v1/first-frame` - gets the first frame of a specific movie
  - `GET /resize-api/v1/trace-movie` - initiates tracing of a plant movie

* When a movie is tracked:
  * Get the desired rotation from dynamoDB
  * Get the starting frame number
  * Download the movie
  * for each from tracking_start to the end:
    * If prev_frame is set, track the points from the last frame to
      the current frame.
    * Write the frame into the zip file
    * Remember the trackpoints
    * Render the points onto the frame
    * writes the rendered frames to a rendered mpeg
  * When finished, the rendered mpeg and the zip file are uploaded to
    s3 and the tracking mode of the movie is turned .

**Video processing:** All rotate, scale, frame extraction, and tracking use **cv2 + Pillow only**. The Lambda does not bundle or use ffmpeg. Any ffmpeg-related code in the repo is legacy (e.g. for local CLI or tests).

Core functionality:
- Invoked via HTTP API. When processing is requested (e.g. after upload), can process (see below).
- **Rotate-and-zip**: POST ``action=rotate-and-zip`` with ``movie_id`` and ``rotation_steps`` (1–3). Rotates the movie using PyAV + Pillow only (no ffmpeg binary; keeps deployment small), uploads the rotated movie back to S3, builds a zip of all frames, uploads the zip, and updates DynamoDB with full metadata (width, height, fps, total_frames, total_bytes; width/height are swapped for 90°/270°). The VM does not rotate or build zip; it only updates ``rotation_steps`` and triggers this Lambda.
- Accepts resize requests with an S3 URL
  - Process
- Process an AWS URL:
  - Check for version number metadata. If present, stop
  - Resize if necessary
  - Add to DynamoDB if not already present
  - Add metadata 'processed' with version
  - Resize if necessary
  - Add to DynamoDB if not already present
- Maintains a log of actions in {prefix}-logs table
- Get log entries (does it need authentication? Not right now)


Resize code base:
- AWS SAM, modeled on https://github.com/Harvard-CSCI-E-11/spring26/tree/main/etc/e11-cli/lambda-home
- lambda function serves as API endpoints
- HTTP access point
- ../src/app/* vended into app/src as necessary


# Data Management

Movies:
------
- Every movie has its mpeg file, its zipfile, and its `keyframe`. Each are stored at predictable locations:
  - movie: course_id/movie_id.mpeg
  - zipfile:  course_id/movie_id.zip
  - keyframe: course_id/movie_id.keyframe.jpeg

- The tracking Lambda builds the JPEG animation zip. When tracking continues in later batches, the Lambda reads the existing zip from S3, copies its members into a fresh temporary zip, appends the new batch frames, and then writes the updated zip back to S3.


Movie Metadata
--------------
We use the x-planttracer: metadata tag to determine if a movie has been procesed or not.

To read:
```
import boto3

s3 = boto3.client('s3')
resp = s3.head_object(Bucket='my-bucket', Key='my-key')
print(resp['Metadata'].get('x-planttracer'))
```

To update to a current image, you must do a self-copy:
```
import boto3

s3 = boto3.client('s3')

bucket = 'my-bucket'
key = 'my-key'

# Get existing metadata (optional, to preserve it)
head = s3.head_object(Bucket=bucket, Key=key)
metadata = head['Metadata']
metadata['x-planttracer'] = 'true'  # Add or update your custom field

# Copy object onto itself with replaced metadata
s3.copy_object(
    Bucket=bucket,
    Key=key,
    CopySource={'Bucket': bucket, 'Key': key},
    Metadata=metadata,
    MetadataDirective='REPLACE'
)
```

When writing it new:
```
import boto3

s3 = boto3.client('s3')

bucket = 'my-bucket'
key = 'my-key'
buf = b'some binary data'

s3.put_object(
    Bucket=bucket,
    Key=key,
    Body=buf,
    Metadata={
        'x-planttracer': 'true'
    },
    ContentType='application/octet-stream'
)
```


Notes:
=====
OpenCV reads colors in BGR (Blue, Green, Red) format, while
Pillow expects RGB. You must swap the colors first, otherwise your
image will look like a smurf!
