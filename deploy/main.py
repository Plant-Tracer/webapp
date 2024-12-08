"""
Application file for FastAPI.

Debug points:

BASE=https://2onng01pv7.execute-api.us-east-1.amazonaws.com/Prod
curl $BASE/docs
curl $BASE/redocs
curl $BASE/fastapi.json


If we give up on FastAPI, consider this to make the old Bottle code run:
* https://pypi.org/project/apig-wsgi/

"""

# pylint: disable=too-many-lines
# pylint: disable=too-many-return-statements

import uvicorn
import os
import platform
import logging
import sys
import filetype

from urllib.parse import urlparse

from fastapi import FastAPI,Request
from fastapi.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from mangum import Mangum

import clogging

from paths import STATIC_DIR,TEMPLATE_DIR
from constants import C,__version__,GET,GET_POST

logging.error("** COLDSTART **")

# templates = Jinja2Templates(directory=TEMPLATE_DIR)


"""
def dump_vars():
    for (k,v) in sorted(os.environ.items()):
        logging.error("%s=%s",k,v)

def dump_files(path="."):
    for (root, dirs, files) in os.walk(path):
        for fn in files:
            logging.error("%s/%s",root,fn)

"""
appx = FastAPI(servers=[
    {"url":"https://2onng01pv7.execute-api.us-east-1.amazonaws.com/Prod","description":"Production Environment"},
    {"url":"http://127.0.0.1:8000","description":"Local"}
    ],
              rootpath='/',
              root_path_in_servers=False)

app = FastAPI()
logging.error("mounting %s",STATIC_DIR)
app.mount("/static", StaticFiles(directory="static"), name='static')

@app.get("/")
def read_root():
    return {"message": "FastAPI running on AWS Lambda and is executed in region " +
            os.environ.get("AWS_REGION","n/a") +
            ", using runtime environment " +
            os.environ.get("AWS_EXECUTION_ENV","n/a")}

@app.get('/index.html')
async def r(request: Request) -> dict:
    return templates.TemplateResponse("index.html", {'request':request, 'foo':'bar', 'platform':platform})

lambda_handler = Mangum(app, lifespan="off")

# Run a local webserver with uvicorn
if __name__ == "__main__":
    uvicorn.run("main:app", port=8000, reload=True)
