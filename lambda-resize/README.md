This directory is for resizer

Ground rules:
- Watches AWS S3. When a movie is uploaded:
  - Resize if necessary
  - Add to DynamoDB


Resize code base:
- AWS SAM, modeled on https://github.com/Harvard-CSCI-E-11/spring26/tree/main/etc/e11-cli/lambda-home
- lambda function serves as API endpoints
- ../src/app/* vended into app/src as necessary
