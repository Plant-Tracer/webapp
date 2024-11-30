import os
import platform
import logging

from fastapi import FastAPI,Request
from mangum import Mangum

# Automatically determine root_path from API Gateway stage
logging.error("Hello World")

def dump_vars():
    for (k,v) in sorted(os.environ.items()):
        logging.error("%s=%s",k,v)

def dump_files(path="."):
    for (root, dirs, files) in os.walk(path):
        for fn in files:
            logging.error("%s/%s",root,fn)

root_path = "/Prod"


logging.error("** COLD START. root_path=%s",root_path)

app = FastAPI(root_path=root_path)


@app.get("/")
def read_root():
    return {"message": "FastAPI running on AWS Lambda and is executed in region " + os.environ["AWS_REGION"] +
            ", using runtime environment " + os.environ["AWS_EXECUTION_ENV"]}

@app.get('/index.html')
async def r(request: Request) -> dict:
    return templates.TemplateResponse("index.html", {'request':request, 'foo':'bar', 'platform':platform})

lambda_handler = Mangum(app, lifespan="off")
