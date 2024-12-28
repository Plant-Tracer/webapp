FROM --platform=linux/amd64 public.ecr.aws/lambda/python:3.11

WORKDIR /app

# Copy deploy/requirements.txt file for deployed app requirements
COPY requirements.txt .

RUN python3 -m pip install -r requirements.txt -t . --no-warn-script-location

# Copy the the app
COPY *.py       ./deploy/
COPY etc/       ./deploy/etc/
COPY static/    ./deploy/static/
COPY templates/ ./deploy/templates/

# CMD is used for local deployment:
CMD ["deploy.lambda_handler.lambda_handler"]
