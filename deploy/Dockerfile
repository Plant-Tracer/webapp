FROM public.ecr.aws/lambda/python:3.11

COPY requirements.txt ./

RUN python3.11 -m pip install -r requirements.txt -t .

COPY *.py ./
COPY etc/*       ./etc/
COPY static/*    ./static/
COPY static/demo ./static/demo/
COPY static/test ./static/test/
COPY templates/* ./templates/


# Command can be overwritten by providing a different command in the template directly.
CMD ["lambda_handler.lambda_handler"]
