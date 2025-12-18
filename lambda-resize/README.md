# lambda-resize

This is a simple AWS lambda function that watches an AWS S3 bucket for new objects to be created.


## Functional Specifications

### VideoUploadCheck
When an object is created it gets an event that:

1. Reads the metadata of the object to see if 1) it is a movie and 2) if it was not previously processed with this script. (This prevents loops)

2. Downloads the movie into the temp directory on the Lambda server.

3. Goes through the movie frame-by-frame and:

   1. Shrinks the frame to the predetermined size (probably 640x480)
   2. Creates a JPEG.
   3. OCRs the frame to see if there is a timestamp in it. If so, and if it matches a timestamp format, add that time to the JPEGs EXIF.
   4. Adds the shrunken frame to a ZIP file as a JPEG.
   5. Writes the frame to a new movie (which will be lower resolution)
   6. Writes a log of actions to the {prefix}-logs table

   The video processing is done with OpenCV.

4. Writes the movie back to the same location in S3.

5. Updates DynamoDB to indicate that the movie was received. (Will be useful when uploads are directly to S3, and not proxied through the app.


### VideoUploadStats
This is an HTTP endpoint that provides the following functionality:
- Version number
- Dump of recent upload logs

## Implementation Notes

- Neither use Flask
- SAM Modeled on https://github.com/Harvard-CSCI-E-11/spring26/tree/main/etc/e11-cli/lambda-home
- lambda function serves as API endpoints
- HTTP access point
- ../src/app/* vended into app/src as necessary


Movies:
------
- Every movie has its mpeg file, its zipfile, and its `keyframe`. Each are stored at predictable locations:
  - movie: course_id/movie_id.mpeg
  - zipfile:  course_id/movie_id.zip
  - keyframe: course_id/movie_id.keyframe.jpeg


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
