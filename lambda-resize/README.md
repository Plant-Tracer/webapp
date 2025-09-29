# lambda-resize
This is the AWS SAM project directory for the lambda function that:
- Watches an S3 bucket under /upload
- Matches the /upload request with a record in DynamoDB that tells:
  - Who did the upload
  - The course_id and movie_id for which the upload is destined.
- Resizes the movie
- Moves the movie into the correct location in the S3 bucket
- Updates the DynamoDB movies table with the new S3 URI.
