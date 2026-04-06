"""
Test the various functions in the database involving movie creation.
"""

import os
import uuid
import copy
import re
import urllib
from urllib.parse import quote
import json

import requests
import filetype
import pytest

from app import odb
from app import s3_presigned
from app import odb_movie_data
from app import apikey

from app.odb import API_KEY,MOVIE_ID,USER_ID
from app.constants import MIME
from app.s3_presigned import s3_client
from app.constants import logger
from .conftest import get_movie_bytes

# Get constants from fixtures (fixtures themselves are in conftest.py)
from .constants import TEST_PLANTMOVIE_PATH, MOVIE_TITLE



POST_TIMEOUT = 2
GET_TIMEOUT = 2

################################################################
## support functions
################################################################

def is_jpeg(buf):
    try:
        return filetype.guess(buf).mime==MIME.JPEG
    except AttributeError:
        logger.error("buf=%s",buf)
        raise

def is_mp4(buf):
    try:
        return filetype.guess(buf).mime==MIME.MP4
    except AttributeError:
        logger.error("buf=%s",buf)
        raise


def movie_list(the_client, api_key):
    """Return a list of the movies"""
    resp = the_client.post('/api/list-movies',
                           data = {'api_key': api_key})
    res = resp.get_json()
    logger.debug("res=%s",res)
    logger.debug("movie_list res=%s",res)
    assert res['error'] is False
    return res['movies']

def get_movie(the_client, api_key, movie_id):
    """Used for testing. Just pull the specific movie"""
    for movie in movie_list(the_client, api_key):
        if movie['movie_id']==movie_id:
            return movie
    raise RuntimeError(f"No movie has movie_id {movie_id}")


def data_from_redirect(url, the_client):
    logger.info("REDIRECT: url=%s ",url)
    url = url.replace("#REDIRECT ","")
    o = urllib.parse.urlparse(url)
    if url.startswith('/api/get-object?'):
        # Decode the /get-object parameters and run the /api/get-object
        m = re.search("urn=(.*)&sig=(.*)",url)
        urn = urllib.parse.unquote(m.group(1))
        sig = urllib.parse.unquote(m.group(2))
        resp = the_client.get(f'/api/get-object?urn={quote(urn)}&sig={quote(sig)}')
        logger.debug("returning resp.data len=%s",len(resp.data))
        return resp.data
    if url.startswith('http'):
        # Request it using http:, which is probably a call to S3
        r = requests.get(url,timeout=GET_TIMEOUT)
        return r.content # note that Flask uses r.data but requests uses r.content
    if url.startswith('s3:'):
        return s3_client().get_object(Bucket=o.netloc, Key=o.path[1:])['Body'].read()
    raise ValueError(f"cannot decode {url}")

################################################################

# Test for edge cases
def test_edge_case(new_movie):
    with pytest.raises(ValueError):
        s3_presigned.make_urn(object_name="xxx",scheme='xxx')

class DummyContext:
    def __init__(self):
        self.function_name = "test_movie_function"
        self.memory_limit_in_mb = 128
        self.invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:test"
        self.aws_request_id = "52fdfc07-2182-154f-163f-5f0f9a621d72"

def test_new_movie(client, new_movie):
    cfg = copy.copy(new_movie)
    movie_id = cfg[MOVIE_ID]
    movie_title = cfg[MOVIE_TITLE]
    api_key = cfg[API_KEY]

    # Did the movie appear in the list?
    movies = movie_list(client, api_key)
    count = 0
    logger.debug("movies=%s",movies)
    for movie in movies:
        if (movie['deleted'] == 0) and (movie['published'] == 0) and (movie['title'] == movie_title):
            count += 1
            logger.debug("found movie: %s",movie)
        else:
            logger.debug("skip deleted=%s published=%s title=%s ",
                          movie['deleted']==0,
                          movie['published']==0,
                          movie['title']==movie_title)
    assert count==1

    # Make sure that we cannot delete the movie with a bad key
    resp = client.post('/api/delete-movie',
                           data = {'api_key': 'invalid',
                                   'movie_id': movie_id})
    assert resp.status_code == 403

    # Make sure that we can get the metadata
    resp = client.post('/api/get-movie-metadata',
                           data = {'api_key': api_key,
                                   'movie_id': movie_id})
    res = resp.get_json()
    logger.debug('json res=%s',json.dumps(res,indent=2))
    assert res['error'] is False
    assert res['metadata']['title'] == movie_title
    assert len(res['metadata']['movie_data_urn']) > 0 # should have a urn!

    movie_data_url = res['metadata']['movie_data_url']
    logger.debug("movie_data_url=%s",movie_data_url)
    assert movie_data_url is not None
    r = requests.get(movie_data_url, timeout=GET_TIMEOUT)
    movie_data = r.content

    # movie_data is now a movie. We should validate it.
    logger.debug("len(movie_data)=%s first 1024:%s",len(movie_data),movie_data[0:1024])
    assert len(movie_data)>0
    assert is_mp4(movie_data)


def test_movie_upload_presigned_post(client, new_course, local_s3):
    """This tests a movie upload by getting the signed URL and then posting to it. It forces the object store"""
    cfg = copy.copy(new_course)
    api_key = cfg[API_KEY]
    movie_title = f'test-movie title {str(uuid.uuid4())}'
    with open(TEST_PLANTMOVIE_PATH, "rb") as f:
        movie_data = f.read()
    movie_data_sha256 = s3_presigned.sha256_hash(movie_data)
    resp = client.post('/api/new-movie',
                           data = {'api_key': api_key,
                                   "title": movie_title,
                                   "description": "test movie description",
                                   "movie_data_sha256":movie_data_sha256
                                   })
    res = resp.get_json()
    assert res['error'] is False

    # Now try the upload post
    assert 'presigned_post' in res

    odb_movie_data.purge_movie(movie_id = res['movie_id'])
    logger.info("PURGE MOVIE %s",res['movie_id'])


def test_movie_update_metadata(client, new_movie):
    """try updating the metadata, and making sure some updates fail."""
    cfg = copy.copy(new_movie)
    movie_id = cfg[MOVIE_ID]
    movie_title = cfg[MOVIE_TITLE]
    api_key = cfg[API_KEY]

    # Validate the old title
    assert get_movie(client, api_key, movie_id)['title'] == movie_title

    new_title = 'special new title ' + str(uuid.uuid4())
    resp = client.post('/api/set-metadata',
                           data = {'api_key': api_key,
                                   'set_movie_id': movie_id,
                                   'property': 'title',
                                   'value': new_title})
    res = resp.get_json()
    logger.debug("res=%s",res)
    assert res['error'] is False

    # Get the list of movies
    assert get_movie(client, api_key, movie_id)['title'] == new_title

    new_description = 'special new description ' + str(uuid.uuid4())
    resp = client.post('/api/set-metadata',
                           data = {'api_key': api_key,
                                   'set_movie_id': movie_id,
                                   'property': 'description',
                                   'value': new_description})
    res = resp.get_json()
    assert res['error'] is False
    assert get_movie(client, api_key, movie_id)['description'] == new_description

    # Try to set the movie's metadata to 'deleted'
    resp = client.post('/api/set-metadata',
                           data = {'api_key': api_key,
                                   'set_movie_id': movie_id,
                                   'property': 'deleted',
                                   'value': 1})
    res = resp.get_json()
    logger.debug("after set deleted=1 res=%s",res)
    assert res['error'] is False
    movie = get_movie(client, api_key, movie_id)
    logger.debug("get_movie(%s,%s,%s)=%s",client,api_key,movie_id,movie)
    assert movie['deleted'] == 1

    # Undelete the movie
    resp = client.post('/api/set-metadata',
                           data = {'api_key': api_key,
                                   'set_movie_id': movie_id,
                                   'property': 'deleted',
                                   'value': 0})
    res = resp.get_json()
    assert res['error'] is False

    # Get the movie's to make sure that it is now deleted
    movie = get_movie(client, api_key, movie_id)
    logger.debug("get_movie(%s,%s,%s)=%s",client,api_key,movie_id,movie)
    assert movie['deleted'] == 0

    # Try to publish the movie under the user's API key. This should not work
    assert get_movie(client, api_key, movie_id)['published'] == 0
    resp = client.post('/api/set-metadata',
                           data = {'api_key': api_key,
                                   'set_movie_id': movie_id,
                                   'property': 'published',
                                   'value': 1})
    res = resp.get_json()
    assert res['error'] is False
    movie = get_movie(client, api_key, movie_id)
    logger.debug("movie=%s",movie)
    assert movie[MOVIE_ID] == movie_id
    assert movie['published'] == 1

@pytest.mark.skip(reason='logging disabled on move to DynamoDB')
def test_log_search_movie(new_movie):
    cfg        = copy.copy(new_movie)
    #api_key    = cfg[API_KEY]
    user_id    = cfg[USER_ID]
    #movie_id   = cfg[MOVIE_ID]
    #movie_title= cfg[MOVIE_TITLE]

    #dbreader = get_dbreader()
    #res = dbfile.DBMySQL.csfr(dbreader, "select user_id from movies where id=%s", (movie_id,))
    res = odb.get_logs( user_id=user_id)
    logger.info("log entries for movie:")
    for r in res:
        logger.info("%s",r)

# pytest: disable=too-many-locals
def test_new_movie_api(client, new_course):
    """Create a new movie_id and return it.
    This uses the movie API where the movie is uploaded with the
    When we are finished with the movie, purge it and all of its child data.
    """
    cfg = copy.copy(new_course)
    api_key = cfg[API_KEY]
    api_key_invalid = api_key+"invalid"
    movie_title = f'test-movie title {str(uuid.uuid4())}'

    logger.debug("new_movie fixture: Opening %s",TEST_PLANTMOVIE_PATH)
    with open(TEST_PLANTMOVIE_PATH, "rb") as f:
        movie_data   = f.read()
        movie_data_sha256 = s3_presigned.sha256_hash(movie_data)
    assert len(movie_data) == os.path.getsize(TEST_PLANTMOVIE_PATH)
    assert len(movie_data) > 0

    # Check for invalid API key handling
    resp = client.post('/api/new-movie',
                           data = {'api_key': api_key_invalid,
                                   "title": movie_title,
                                   "description": "test movie description",
                                   "movie_data_sha256": movie_data_sha256})
    logger.debug("invalid api_key resp=%s",resp)
    logger.debug("invalid api_key resp.text=%s",resp.text)
    logger.debug("invalid api_key resp.json=%s",resp.json)
    assert 'error' in resp.get_json()
    assert resp.get_json()['error'] is True

    # Check for invalid SHA256 handling
    resp = client.post('/api/new-movie',
                           data = {'api_key': api_key,
                                   "title": movie_title,
                                   "description": "test movie description",
                                   "movie_data_sha256": movie_data_sha256+"-invalid"})
    assert resp.get_json()['error'] is True

    # Get the upload information
    resp = client.post('/api/new-movie',
                           data = {'api_key': api_key,
                    "title": movie_title,
                    "description": "test movie description",
                    "movie_data_sha256": movie_data_sha256})
    res = resp.get_json()
    assert res['error'] is False
    movie_id = res['movie_id']
    assert odb.is_movie_id(movie_id)

    logger.debug("new_movie fixture: movie_id=%s",movie_id)
    cfg[MOVIE_ID] = movie_id
    cfg[MOVIE_TITLE] = movie_title

    url    = res['presigned_post']['url']
    fields = res['presigned_post']['fields']

    logger.debug("new_movie fixture: url=%s fields=%s",url,fields)

    # Now send the data
    with open(TEST_PLANTMOVIE_PATH, "rb") as f:
        # Do a real post! (probably going to S3)
        logger.debug("calling requests.post(%s,data=%s)",url,fields)
        r = requests.post(url, files={'file':f}, data=fields, timeout=POST_TIMEOUT)
        logger.info("uploaded to %s r=%s",url, r)
        assert r.ok

    # Make sure data got there
    logger.debug("new_movie fixture: movie uploaded")
    retrieved_movie_data = get_movie_bytes(movie_id)
    assert len(movie_data) == len(retrieved_movie_data)
    assert movie_data == retrieved_movie_data

    logger.debug("new_movie fixture: Delete the movie we uploaded")
    resp = client.post('/api/delete-movie',
                           data={'api_key': api_key,
                                 'movie_id': movie_id})
    res = resp.get_json()
    assert res['error'] is False

    logger.debug("new_movie fixture: Purge the movie that we have deleted")
    odb_movie_data.purge_movie(movie_id=movie_id)
    logger.debug("new_movie fixture: done")


def test_new_movie_attribution_paths(client, new_course, local_s3):
    """Test the three attribution paths: no research use, research anonymous, research with attribution."""
    cfg = copy.copy(new_course)
    api_key = cfg[API_KEY]
    with open(TEST_PLANTMOVIE_PATH, "rb") as f:
        movie_data = f.read()
    movie_data_sha256 = s3_presigned.sha256_hash(movie_data)
    base_data = {
        "api_key": api_key,
        "title": f"attribution-test-{uuid.uuid4()}",
        "description": "test description",
        "movie_data_sha256": movie_data_sha256,
    }

    # Path 1: May not be used in research (no research use)
    resp1 = client.post("/api/new-movie", data={**base_data, "title": f"path1-{uuid.uuid4()}"})
    res1 = resp1.get_json()
    assert res1["error"] is False
    movie_id1 = res1["movie_id"]
    movie1 = odb.get_movie(movie_id=movie_id1)
    assert movie1["research_use"] == 0
    assert movie1["credit_by_name"] == 0
    assert movie1.get("attribution_name") is None
    pp1 = res1["presigned_post"]
    assert pp1["fields"].get("x-amz-meta-research-use") == "0"
    assert pp1["fields"].get("x-amz-meta-credit-by-name") == "0"
    assert pp1["fields"].get("x-amz-meta-attribution-name") == ""
    resp = client.post("/api/delete-movie", data={"api_key": api_key, "movie_id": movie_id1})
    assert resp.get_json()["error"] is False
    odb_movie_data.purge_movie(movie_id=movie_id1)

    # Path 2: May be used in research but anonymously
    resp2 = client.post(
        "/api/new-movie",
        data={**base_data, "title": f"path2-{uuid.uuid4()}", "research_use": "1"},
    )
    res2 = resp2.get_json()
    assert res2["error"] is False
    movie_id2 = res2["movie_id"]
    movie2 = odb.get_movie(movie_id=movie_id2)
    assert movie2["research_use"] == 1
    assert movie2["credit_by_name"] == 0
    assert movie2.get("attribution_name") is None
    pp2 = res2["presigned_post"]
    assert pp2["fields"].get("x-amz-meta-research-use") == "1"
    assert pp2["fields"].get("x-amz-meta-credit-by-name") == "0"
    assert pp2["fields"].get("x-amz-meta-attribution-name") == ""
    resp = client.post("/api/delete-movie", data={"api_key": api_key, "movie_id": movie_id2})
    assert resp.get_json()["error"] is False
    odb_movie_data.purge_movie(movie_id=movie_id2)

    # Path 3: May be used in research with attribution to "Alyssa P. Hacker"
    resp3 = client.post(
        "/api/new-movie",
        data={
            **base_data,
            "title": f"path3-{uuid.uuid4()}",
            "research_use": "1",
            "credit_by_name": "1",
            "attribution_name": "Alyssa P. Hacker",
        },
    )
    res3 = resp3.get_json()
    assert res3["error"] is False
    movie_id3 = res3["movie_id"]
    movie3 = odb.get_movie(movie_id=movie_id3)
    assert movie3["research_use"] == 1
    assert movie3["credit_by_name"] == 1
    assert movie3.get("attribution_name") == "Alyssa P. Hacker"
    pp3 = res3["presigned_post"]
    assert pp3["fields"].get("x-amz-meta-research-use") == "1"
    assert pp3["fields"].get("x-amz-meta-credit-by-name") == "1"
    assert pp3["fields"].get("x-amz-meta-attribution-name") == "Alyssa P. Hacker"
    resp = client.post("/api/delete-movie", data={"api_key": api_key, "movie_id": movie_id3})
    assert resp.get_json()["error"] is False
    odb_movie_data.purge_movie(movie_id=movie_id3)


def test_api_edit_movie(new_movie, client):
    """Verify edit-movie: invalid action/auth fail; valid rotate90cw updates rotation_steps and triggers Lambda.
    VM only updates rotation_steps and clears tracking; rotation/zip run in Lambda."""
    api_key = new_movie[API_KEY]
    movie_id = new_movie[MOVIE_ID]

    movie = odb.get_movie(movie_id=movie_id)
    movie_metadata = odb.get_movie_metadata(movie_id=movie_id)
    logger.debug("movie=%s movie_metadata=%s", movie, movie_metadata)

    assert movie['user_id'] == new_movie[USER_ID]

    userdict = apikey.user_dict_for_api_key(new_movie[API_KEY])
    assert userdict[USER_ID] == new_movie[USER_ID], f"userdict={userdict} new_movie={new_movie}"

    # Invalid action
    data = {'api_key': api_key, 'movie_id': movie_id, 'rotation': '500'}
    resp = client.post('/api/rotate-movie', data=data)
    assert resp.json['error'] is True, f"resp.json={resp.json} data={data}"
    movie = odb.get_movie(movie_id=movie_id)
    assert movie.get('rotation', 0) == 0

    # Invalid api_key
    data = {'api_key': "bad-api-key", 'movie_id': movie_id, 'rotation': '0'}
    resp = client.post('/api/rotate-movie', data=data)
    assert resp.json['error'] is True, f"resp.json={resp.json} data={data}"

    # Success: rotation_steps omitted => 1 step
    data = {'api_key': api_key, 'movie_id': movie_id, 'rotation': '90'}
    resp = client.post('/api/rotate-movie', data=data)
    assert resp.json['error'] is False, f"resp.json={resp.json} data={data}"
    movie = odb.get_movie(movie_id=movie_id)
    assert movie.get('rotation') == 90, f"{movie}"

    # Success: rotation_steps=2
    data = {'api_key': api_key, 'movie_id': movie_id, 'rotation': '180'}
    resp = client.post('/api/rotate-movie', data=data)
    assert resp.json['error'] is False, f"resp.json={resp.json} data={data}"
    movie = odb.get_movie(movie_id=movie_id)
    assert movie.get('rotation') == 180, f"{movie}"

    movie_metadata2 = odb.get_movie_metadata(movie_id=movie_id)
    logger.debug("movie_metadata2=%s", movie_metadata2)
    assert movie_metadata2.get('rotation') == 180, f"{movie}"


def test_get_movie_metadata_rotation_coercion(new_movie):
    """Verify that get_movie_metadata coerces rotation to int, defaulting to 0 for invalid values,
    and swaps width/height only when rotation is 90 or 270."""
    movie_id = new_movie[MOVIE_ID]

    # Seed width and height so we can detect swaps
    odb.set_movie_metadata(movie_id=movie_id, movie_metadata={'width': 100, 'height': 200})

    # String "90" should be coerced to int 90 → dimensions swapped
    odb.set_movie_metadata(movie_id=movie_id, movie_metadata={'rotation': '90'})
    meta = odb.get_movie_metadata(movie_id=movie_id)
    assert meta.get('width') == 200
    assert meta.get('height') == 100

    # Invalid string → coerced to 0 → no swap
    odb.set_movie_metadata(movie_id=movie_id, movie_metadata={'rotation': 'invalid'})
    meta = odb.get_movie_metadata(movie_id=movie_id)
    assert meta.get('width') == 100
    assert meta.get('height') == 200

    # None → coerced to 0 → no swap
    odb.set_movie_metadata(movie_id=movie_id, movie_metadata={'rotation': None})
    meta = odb.get_movie_metadata(movie_id=movie_id)
    assert meta.get('width') == 100
    assert meta.get('height') == 200

    # String "270" should be coerced to int 270 → dimensions swapped
    odb.set_movie_metadata(movie_id=movie_id, movie_metadata={'rotation': '270'})
    meta = odb.get_movie_metadata(movie_id=movie_id)
    assert meta.get('width') == 200
    assert meta.get('height') == 100

    # String "180" should be coerced to int 180 → no swap
    odb.set_movie_metadata(movie_id=movie_id, movie_metadata={'rotation': '180'})
    meta = odb.get_movie_metadata(movie_id=movie_id)
    assert meta.get('width') == 100
    assert meta.get('height') == 200
