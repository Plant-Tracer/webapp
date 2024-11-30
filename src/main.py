import os
import platform
import logging

from fastapi import FastAPI,Request
from mangum import Mangum

logging.error("** STARTING UP")

app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "FastAPI running on AWS Lambda and is executed in region " + os.environ["AWS_REGION"] + ", using runtime environment " + os.environ["AWS_EXECUTION_ENV"]}

@app.get('/index.html')
async def r(request: Request) -> dict:
    return templates.TemplateResponse("index.html", {'request':request, 'foo':'bar', 'platform':platform})

lambda_handler = Mangum(app, lifespan="off")
