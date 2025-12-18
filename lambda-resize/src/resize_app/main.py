"""
Main entry point for AWS Lambda Dashboard

Generate the https://camera.planttracer.org/ home page.
Runs the camera.
"""

# at top of home_app/home.py (module import time)
import base64
import binascii
import json
import os
from os.path import splitext
import sys
import time
import uuid
import datetime
import tempfile
from typing import Any, Dict, Tuple, Optional, TYPE_CHECKING
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from .common import LOGGER
from .resize import video_unpack_resize
from .src.app.constants import MIME

ZIP_TEMPLATE="{base}.zip"
FRAME_TEMPLATE="{base}.mov_frame{frame_number:04}.jpeg"
RESIZED_TEMPLATE="{base}.rmov"

__version__ = "0.1.0"

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client
    from mypy_boto3_dynamodb import DynamoDBClient
    from mypy_boto3_dynamodb.service_resource import DynamoDBServiceResource, Table as DynamoDBTable
else:
    S3Client = Any                 # pylint: disable=invalid-name
    DynamoDBClient = Any           # pylint: disable=invalid-name
    DynamoDBServiceResource = Any  # pylint: disable=invalid-name
    DynamoDBTable = Any            # pylint: disable=invalid-name


################################################################
## We have resized this
PLANTTRACER_HEADER = 'Planttracer'

################################################################
## Minimal support for a Python-based website in Lamda with jinja2 support
##

# jinja2
AWS_REGION = os.environ.get("AWS_REGION","us-east-1")
LAMBDA_LOGS_TABLE_NAME    = os.environ.get("LAMBDA_LOGS_TABLE_NAME","resize-app-lambda-logs")
s3_client : S3Client = boto3.client("s3", region_name=AWS_REGION)
dynamodb_client : DynamoDBClient = boto3.client("dynamodb", region_name=AWS_REGION)
dynamodb_resource : DynamoDBServiceResource = boto3.resource( 'dynamodb', region_name=AWS_REGION )
logs_table : DynamoDBTable   = dynamodb_resource.Table(LAMBDA_LOGS_TABLE_NAME)


def resp_json( status: int, body: Dict[str, Any], headers: Optional[Dict[str, str]] = None ) -> Dict[str, Any]:
    """End HTTP event processing with a JSON object"""
    LOGGER.debug("resp_json(status=%s) body=%s", status, body)
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            **(headers or {}),
        },
        "body": json.dumps(body),
    }


def _with_request_log_level(payload: Dict[str, Any]):
    """Context manager to temporarily adjust log level from JSON (log_level or LOG_LEVEL)."""
    class _Ctx:
        def __init__(self):
            self.old = LOGGER.level

        def __enter__(self):
            lvl = payload.get("log_level") or payload.get("LOG_LEVEL")
            if isinstance(lvl, str):
                LOGGER.setLevel(lvl)
            return self

        def __exit__(self, exc_type, exc, tb):
            LOGGER.setLevel(self.old)

    return _Ctx()


################################################################
## api code.
## api calls do not use sessions. Authenticated APIs (e.g. api_register, api_grade)
## authenticate with api_authenticate(payload), which returns the user directory.

def api_heartbeat(event, context)  -> Dict[str, Any]:
    """Called periodically. Not authenticated. Main purpose clean up active camera sessions"""
    LOGGER.info("heartbeat event=%s context=%s", event, context)
    return resp_json( 200, { "now": time.time() } )


################################################################
## Parse Lambda Events and cookies
def parse_http_event(event: Dict[str, Any]) -> Tuple[str, str, Dict[str, Any]]:
    """parse HTTP API v2 event.
    :param event: AWS Lambda HTTP API v2 event to parse
    :return (method,path,payload) - method - HTTP Method; path=HTTP Path; payload=JSON body if POST
    """
    stage = event.get("requestContext", {}).get("stage", "")
    path = event.get("rawPath") or event.get("path") or "/"
    if stage and path.startswith("/" + stage):
        path = path[len(stage) + 1 :] or "/"
    method = (
        event.get("requestContext", {})
        .get("http", {})
        .get("method", event.get("httpMethod", "GET"))
    )
    body = event.get("body")
    if event.get("isBase64Encoded"):
        try:
            body = base64.b64decode(body or "").decode("utf-8", "replace")
        except binascii.Error:
            body = None
    try:
        payload = json.loads(body) if body else {}
    except json.JSONDecodeError:
        payload = {}
    return method, path, payload


def write_log( message, *, course_id=None, log_user_id=None, ipaddr=None):
    log_id = str(uuid.uuid4())
    now = datetime.datetime.now().isoformat()
    print("logs_table=",logs_table)
    logs_table.put_item(Item={'log_id':log_id,
                              'datetime':now,
                              'message':message,
                              'user_id':log_user_id,
                              'ipaddr':ipaddr,
                              'course_id':course_id})

def api_ping(event, context):
    print("ping")
    write_log('ping')
    return resp_json( 200,
                      { "error": False, "message": "ok", "path": sys.path,
                        "event" : str(event),
                        "context": str(context) } )

def api_log():
    items = []
    kwargs = {}
    while True:
        response = logs_table.scan(**kwargs)
        items.extend(response.get('Items',[]))
        last_evaluated_key = response.get('LastEvaluatedKey')
        if not last_evaluated_key:
            break
        kwargs['ExclusiveStartKey'] = last_evaluated_key
    return resp_json( 400, {"logs":items})
################################################################

def object_exists(bucket:str, key:str) -> bool:
    try:
        print("checking for ",key)
        s3_client.head_object(Bucket=bucket, Key=key)
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        status = e.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if code in {"404", "NoSuchKey", "NotFound"} or status == 404:
            return False
        raise                   # unkown error
    LOGGER.debug("object_exists(%s,%s)=True",bucket,key)
    return True


def api_resize(bucket, s3key_mov)  -> Dict[str, Any]:
    """
    1. See if key has metadata. If so, abort.
    2. Probe for zipfile and first frame. If both exist, abort.
    3. Get movie
    4. Resize, extract first frame and make zipfile.
    5. Upload resized movie, first frame and zipfile, all with metadata

    :param event: - the event, for reporting
    :param s3key: - what should be examined for resizing.

    Exceptions are reported by caller
    """

    LOGGER.info("api_resize bucket=%s s3key_mov=%s", bucket, s3key_mov)
    s3key_base   = splitext(s3key_mov)[0]
    s3key_zipfile= ZIP_TEMPLATE.format(base=s3key_base)
    s3key_frame0 = FRAME_TEMPLATE.format(base=s3key_base,frame_number=0)
    s3key_resized = RESIZED_TEMPLATE.format(base=s3key_base)

    start = time.time()
    try:
        r = s3_client.head_object(Bucket=bucket, Key=s3key_mov)
    except s3_client.exceptions.NoSuchKey:
        LOGGER.error("NoSuchKey: s3://%s/%s", bucket, s3key_mov)
        return resp_json(400, {'error':'NoSuchKey'})

    custom_metadata = {PLANTTRACER_HEADER:"YES"}
    print("METADATA",r.get('Metadata'))
    if r.get('Metadata',{}).get(PLANTTRACER_HEADER):
        LOGGER.info("s3://%s/%s has %s metadata",bucket,s3key_mov,PLANTTRACER_HEADER)
        return resp_json(201, {'message':f'Already has {PLANTTRACER_HEADER} Metadata'})

    # See if the zip file exists
    if object_exists(bucket, s3key_zipfile):
        s3key_zipfile = None        # exists, do not overwrite

    # See if the frame0 file exists
    if object_exists(bucket,s3key_frame0):
        s3key_frame0 = None        # exists, do not overwrite

    with tempfile.TemporaryDirectory() as tempdir:
        print("tempdir=",tempdir)
        infile_path  = Path(tempdir) / "infile.mov"
        outfile_path = Path(tempdir) / "outfile.mov"
        zipfile_path = Path(tempdir) / "zipfile.zip" if s3key_zipfile is not None else None
        frame0_path  = Path(tempdir) / "frame0.jpeg"  if s3key_frame0 is not None else None

        # download the file if we can
        s3_client.download_file(bucket, s3key_mov, str(infile_path))

        # Now process
        LOGGER.info("calling video_unpack_resize infile_path=%s outfile_path=%s frame0_path=%s zipfile_path=%s",
                    infile_path,outfile_path,frame0_path,zipfile_path)
        video_unpack_resize(infile_path = infile_path,
                            outfile_path = outfile_path,
                            frame0_path = frame0_path,
                            zipfile_path = zipfile_path)

        # Upload the artifacts
        LOGGER.info("upload %s --> %s",outfile_path,s3key_resized)
        s3_client.upload_file(Filename=str(outfile_path),
                              Bucket=bucket,
                              Key=s3key_resized,
                              ExtraArgs = {
                                  "Metadata": custom_metadata,
                                  "ContentType":MIME.MP4
                              })

        if zipfile_path is not None and s3key_zipfile is not None:
            LOGGER.info("upload %s --> %s",zipfile_path,s3key_zipfile)
            s3_client.upload_file(Filename=str(zipfile_path),
                                  Bucket=bucket,
                                  Key=s3key_zipfile,
                                  ExtraArgs = {
                                      "Metadata": custom_metadata,
                                      "ContentType":MIME.ZIP
                                  })


        if frame0_path is not None and s3key_frame0 is not None:
            LOGGER.info("upload %s --> %s",frame0_path,s3key_frame0)
            s3_client.upload_file(Filename=str(frame0_path),
                                  Bucket=bucket,
                                  Key=s3key_frame0,
                                  ExtraArgs = {
                                      "Metadata": custom_metadata,
                                      "ContentType":MIME.JPEG
                                  })

    end = time.time()
    LOGGER.info("api_resize completed. start=%s time=%s",start,end-start)
    return resp_json(200, {'start':start, 'time':end-start})





################################################################
## main entry point from lambda system

# pylint: disable=too-many-return-statements, disable=too-many-branches, disable=unused-argument
def lambda_handler(event, context) -> Dict[str, Any]:
    """called by lambda"""

    LOGGER.info("=======================================================================")
    LOGGER.info("LOGGER.info")
    LOGGER.debug("LOGGER.debug")

    print("lambda_handler event=",event,"context=",context)
    for k,v in sorted(os.environ.items()):
        if k in ('AWS_SECRET_ACCESS_KEY','AWS_SESSION_TOKEN'):
            v = '********'
        print(f"{k} = {v}")

    if event.get('source','')=='aws.s3' and event.get('detail-type','')=='Object Created':
        detail = event.get('detail',{})

        request_id = detail.get('request-id','')
        LOGGER.info("request_id=%s",request_id)
        # Make sure this is not a duplicate request

        bucket = detail.get('bucket',{}).get('name')
        key = detail.get('object',{}).get('key')
        if (bucket is None) or (key is None):
            LOGGER.error("bucket=%s key=%s event=%s",bucket,key,event)
            return resp_json(400, {"error":True, 'bucket':bucket, 'key':key})
        return api_resize(bucket, key)

    method, path, payload = parse_http_event(event)
    print("method=",method,"path=",path,"payload=",payload)

    with _with_request_log_level(payload):
        try:
            LOGGER.info( "req method='%s' path='%s' action='%s'", method, path, payload.get("action") )
            action = (payload.get("action") or "").lower()

            match (method, path, action):
                ################################################################
                # JSON API Actions
                #
                case (_, "/api/v1", "ping"):
                    return api_ping(event,context)

                case (_, '/api/v1/ping', _):
                    return api_ping(event,context)

                case ("POST", "/api/v1", "resize-start"):
                    return api_resize(payload.get('bucket'), payload.get('s3key'))

                case (_, "/api/v1", "heartbeat"):
                    return api_heartbeat(event, context)

                case (_, "/api/v1", "log"):
                    return api_log()

                case (_, "/api/v1", _):
                    return resp_json( 400, { "error": True, "message": f"Unknown action {action}"})

                ################################################################
                # error
                case (_, _, _):
                    return resp_json( 400, { "error": True, "message": f"Unknown action {action}"})

        except Exception as e:  # pylint: disable=broad-exception-caught
            LOGGER.exception("Unhandled exception! e=%s", e)

            # Return JSON for API requests
            return resp_json(500, {"error": True, "message": str(e)})
