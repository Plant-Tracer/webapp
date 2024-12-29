# https://docs.aws.amazon.com/lambda/latest/dg/python-image.html

FROM --platform=linux/amd64 public.ecr.aws/lambda/python:3.11

# Copy deploy/requirements.txt file for deployed app requirements
COPY requirements.txt ${LAMBDA_TASK_ROOT}

RUN python3 -m pip install -r requirements.txt -t . --no-warn-script-location

# Copy the the app
COPY *.py       ${LAMBDA_TASK_ROOT}/app/
COPY etc/       ${LAMBDA_TASK_ROOT}/app/etc/
COPY static/    ${LAMBDA_TASK_ROOT}/app/static/
COPY templates/ ${LAMBDA_TASK_ROOT}/app/templates/

# CMD is used for local deployment:
CMD ["app.lambda_handler.handler"]
