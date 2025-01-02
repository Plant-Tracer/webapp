#
# Dockerfile to create the container with the Plant-Tracer app
#
# Note that AWS Lambda deploys the application in /var/task
#

FROM --platform=linux/amd64 public.ecr.aws/lambda/python:3.11

COPY demo.py requirements.txt ./

RUN python3 -m pip install -r requirements.txt -t . --no-warn-script-location

# Copy the the app
COPY ./                ./

# CMD is used for local deployment:
#CMD ["demo.lambda_handler"]
CMD ["lambda_handler.lambda_app"]
