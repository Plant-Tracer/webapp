This directory is for lambda-resize

Core functionality:
- Watches AWS S3. When a movie is uploaded:
  - Process (see below)
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


Movies:
------
- Every movie has its mpeg file, its zipfile, and its `keyframe`. Eachg are stored at predictable locations:
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
