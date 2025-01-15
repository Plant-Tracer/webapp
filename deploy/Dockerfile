#
# Dockerfile to create the container with the Plant-Tracer app
#
# Note that AWS Lambda deploys the application in /var/task
#
# https://docs.aws.amazon.com/lambda/latest/dg/python-image.html

FROM --platform=linux/amd64 public.ecr.aws/lambda/python:3.11



COPY demo.py requirements.txt ./
RUN python3 -m pip install -r requirements.txt -t . --no-warn-script-location

# Copy the the app
COPY *.py       ${LAMBDA_TASK_ROOT}/app/
COPY etc/       ${LAMBDA_TASK_ROOT}/app/etc/
COPY static/    ${LAMBDA_TASK_ROOT}/app/static/
COPY templates/ ${LAMBDA_TASK_ROOT}/app/templates/

CMD ["app.lambda_handler.handler"]
