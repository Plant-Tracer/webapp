"""
Test the various functions in the database involving movie creation.
"""

import sys
import os
import uuid
import logging
import pytest
import uuid
import base64
import time
import copy
import hashlib
import requests
import json
import logging
import re
import urllib
from urllib.parse import quote
from os.path import abspath, dirname

import filetype

import app.db as db
import app.db_object as db_object
import app.bottle_api as bottle_api
import app.bottle_app as bottle_app
import app.dbfile as dbfile
import app.db_object as db_object
import app.tracker as tracker

from app.paths import TEST_DATA_DIR
from app.constants import C,MIME
from app.auth import get_dbreader,get_dbwriter

# Get the fixtures from user_test
from fixtures.app_client import client
from user_test import new_user,new_course,API_KEY,MOVIE_ID,MOVIE_TITLE,USER_ID,DBWRITER,TEST_PLANTMOVIE_PATH
from db_object_test import SaveS3Bucket

################################################################
## support functions
################################################################


def movie_list(the_client, api_key):
    """Return a list of the movies"""
    resp = the_client.post('/api/list-movies',
                           data = {'api_key': api_key})
    res = resp.get_json()
    assert res['error'] == False
    return res['movies']

def get_movie(the_client, api_key, movie_id):
    """Used for testing. Just pull the specific movie"""
    for movie in movie_list(the_client, api_key):
        if movie['movie_id']==movie_id:
            return movie
    raise RuntimeError(f"No movie has movie_id {movie_id}")


@pytest.fixture
def new_movie(client, new_user):
    """Create a new movie_id and return it.
    This uses the movie API where the movie is uploaded with the
    When we are finished with the movie, purge it and all of its child data.
    """
    cfg = copy.copy(new_user)
    api_key = cfg[API_KEY]
    api_key_invalid = api_key+"invalid"
    movie_title = f'test-movie title {str(uuid.uuid4())}'

    logging.debug("new_movie fixture: Opening %s",TEST_PLANTMOVIE_PATH)
    with open(TEST_PLANTMOVIE_PATH, "rb") as f:
        movie_data   = f.read()
        movie_data_sha256 = db_object.sha256(movie_data)
    assert len(movie_data) == os.path.getsize(TEST_PLANTMOVIE_PATH)
    assert len(movie_data) > 0

    # Check for invalid API key handling
    resp = client.post('/api/new-movie',
                           data = {'api_key': api_key_invalid,
                                   "title": movie_title,
                                   "description": "test movie description",
                                   "movie_data_sha256": movie_data_sha256})
    logging.debug("invalid api_key resp=%s",resp)
    logging.debug("invalid api_key resp.text=%s",resp.text)
    logging.debug("invalid api_key resp.json=%s",resp.json)
    assert 'error' in resp.get_json()
    assert resp.get_json()['error'] == True

    # Check for invalid SHA256 handling
    resp = client.post('/api/new-movie',
                           data = {'api_key': api_key,
                                   "title": movie_title,
                                   "description": "test movie description",
                                   "movie_data_sha256": movie_data_sha256+"-invalid"})
    assert resp.get_json()['error']==True

    # Get the upload information
    resp = client.post('/api/new-movie',
                           data = {'api_key': api_key,
                    "title": movie_title,
                    "description": "test movie description",
                    "movie_data_sha256": movie_data_sha256})
    res = resp.get_json()
    assert res['error'] == False
    movie_id = res['movie_id']
    assert movie_id > 0

    logging.debug("new_movie fixture: movie_id=%s",movie_id)
    cfg[MOVIE_ID] = movie_id
    cfg[MOVIE_TITLE] = movie_title

    url    = res['presigned_post']['url']
    fields = res['presigned_post']['fields']

    logging.debug("new_movie fixture: url=%s fields=%s",url,fields)

    # Now send the data
    with open(TEST_PLANTMOVIE_PATH, "rb") as f:
        if url.startswith('https://'):
            # Do a real post! (probably going to S3)
            logging.debug("calling requests.post(%s,data=%s)",url,fields)
            r = requests.post(url, files={'file':f}, data=fields)
            logging.info("uploaded to %s r=%s",url, r)
            assert r.ok
        else:
            # Use the upload-movie api to store in the SQL Database
            fields['file'] = (f,TEST_PLANTMOVIE_PATH)
            resp = client.post('/api/upload-movie',
                                   content_type='multipart/form-data',
                                   data = fields)
            assert resp.status_code == 200
            res = resp.get_json()
            assert res['error']==False

    # Make sure data got there
    logging.debug("new_movie fixture: movie uploaded")
    retrieved_movie_data = db.get_movie_data(movie_id=movie_id)
    assert len(movie_data) == len(retrieved_movie_data)
    assert movie_data == retrieved_movie_data
    logging.debug("new_movie fixture: yield %s",cfg)
    yield cfg

    logging.debug("new_movie fixture: Delete the movie we uploaded")
    resp = client.post('/api/delete-movie',
                           data={'api_key': api_key,
                                 'movie_id': movie_id})
    res = resp.get_json()
    assert res['error'] == False

    logging.debug("new_movie fixture: Purge the movie that we have deleted")
    db.purge_movie(movie_id=movie_id)
    logging.debug("new_movie fixture: done")


def data_from_redirect(url, the_client):
    logging.info("REDIRECT: url=%s ",url)
    url = url.replace("#REDIRECT ","")
    if url.startswith('/api/get-object?'):
        # Decode the /get-object parameters and run the /api/get-object
        m = re.search("urn=(.*)&sig=(.*)",url)
        urn = urllib.parse.unquote(m.group(1))
        sig = urllib.parse.unquote(m.group(2))
        resp = the_client.get(f'/api/get-object?urn={quote(urn)}&sig={quote(sig)}')
        logging.debug("returning resp.data len=%s",len(resp.data))
        return resp.data
    else:
        # Request it using http:, which is probably a call to S3
        r = requests.get(url)
        return r.content # note that Flask uses r.data but requests uses r.content



# Test for edge cases
def test_edge_case():
    with pytest.raises(db.InvalidMovie_Id):
        db.get_movie_data(movie_id = -1)
    with pytest.raises(ValueError):
        db_object.make_urn(object_name="xxx",scheme='xxx')

def test_new_movie(client, new_movie):
    cfg = copy.copy(new_movie)
    movie_id = cfg[MOVIE_ID]
    movie_title = cfg[MOVIE_TITLE]
    api_key = cfg[API_KEY]

    # Did the movie appear in the list?
    movies = movie_list(client, api_key)
    count = 0
    for movie in movies:
        if (movie['deleted'] == 0) and (movie['published'] == 0) and (movie['title'] == movie_title):
            count += 1
            logging.debug("found movie: %s",movie)
    assert count==1

    # Make sure that we cannot delete the movie with a bad key
    resp = client.post('/api/delete-movie',
                           data = {'api_key': 'invalid',
                                   'movie_id': movie_id})
    assert resp.status_code == 403

    # Make sure that we can get data for the movie
    resp = client.post('/api/get-movie-data',
                           data = {'api_key': api_key,
                                   'movie_id': movie_id,
                                   'redirect_inline':True})
    logging.debug("test_new_movie: resp.data[0:10]=%s len=%s",resp.data[0:10],len(resp.data))
    if resp.data[0:10] == b"#REDIRECT ":
        movie_data = data_from_redirect(resp.text, client)
    else:
        movie_data = resp.data

    # movie_data is now a movie. We should validate it.
    logging.debug("len(movie_data)=%s first 1024:%s",len(movie_data),movie_data[0:1024])
    assert len(movie_data)>0
    assert filetype.guess(movie_data).mime==MIME.MP4

    # Make sure that we can get the metadata
    resp = client.post('/api/get-movie-metadata',
                           data = {'api_key': api_key,
                                   'movie_id': movie_id})
    res = resp.get_json()
    assert res['error']==False
    assert res['metadata']['title'] == movie_title



def test_movie_upload_presigned_post(client, new_user,SaveS3Bucket):
    """This tests a movie upload by getting the signed URL and then posting to it. It forces the object store"""
    cfg = copy.copy(new_user)
    api_key = cfg[API_KEY]
    movie_title = f'test-movie title {str(uuid.uuid4())}'
    with open(TEST_PLANTMOVIE_PATH, "rb") as f:
        movie_data = f.read()
    movie_data_sha256 = db_object.sha256(movie_data)
    resp = client.post('/api/new-movie',
                           data = {'api_key': api_key,
                                   "title": movie_title,
                                   "description": "test movie description",
                                   "movie_data_sha256":movie_data_sha256
                                   })
    res = resp.get_json()
    assert res['error'] == False

    # Now try the upload post
    # TODO: boddle didn't have a way to upload post requests, but we do now!
    assert 'presigned_post' in res;

    db.purge_movie(movie_id = res['movie_id'])
    logging.info("PURGE MOVIE %d",res['movie_id'])


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
    assert res['error'] == False

    # Get the list of movies
    assert get_movie(client, api_key, movie_id)['title'] == new_title

    new_description = 'special new description ' + str(uuid.uuid4())
    resp = client.post('/api/set-metadata',
                           data = {'api_key': api_key,
                                   'set_movie_id': movie_id,
                                   'property': 'description',
                                   'value': new_description})
    res = resp.get_json()
    assert res['error'] == False
    assert get_movie(client, api_key, movie_id)['description'] == new_description

    # Try to set the movie's metadata to 'deleted'
    resp = client.post('/api/set-metadata',
                           data = {'api_key': api_key,
                                   'set_movie_id': movie_id,
                                   'property': 'deleted',
                                   'value': 1})
    res = resp.get_json()
    assert res['error'] == False
    assert get_movie(client, api_key, movie_id)['deleted'] == 1

    # Undelete the movie
    resp = client.post('/api/set-metadata',
                           data = {'api_key': api_key,
                                   'set_movie_id': movie_id,
                                   'property': 'deleted',
                                   'value': 0})
    res = resp.get_json()
    assert res['error'] == False
    assert get_movie(client, api_key, movie_id)['deleted'] == 0

    # Try to publish the movie under the user's API key. This should not work
    assert get_movie(client, api_key, movie_id)['published'] == 0
    resp = client.post('/api/set-metadata',
                           data = {'api_key': api_key,
                                   'set_movie_id': movie_id,
                                   'property': 'published',
                                   'value': 1})
    res = resp.get_json()
    assert res['error'] == False
    assert get_movie(client, api_key, movie_id)['published'] == 0

def test_movie_extract1(client, new_movie):
    """Check single frame extarct and error handling"""
    cfg = copy.copy(new_movie)
    movie_id = cfg[MOVIE_ID]
    movie_title = cfg[MOVIE_TITLE]
    api_key = cfg[API_KEY]
    user_id = cfg[USER_ID]

    # Check for insufficient arguments
    # Should produce http403
    resp = client.post('/api/get-frame')
    assert resp.status_code == 403

    r = resp.get_json()

    # Check for invalid frame_number
    logging.debug("test_movie_extract1: point1")
    resp = client.post('/api/get-frame',
                           data = {'api_key': api_key,
                                   'movie_id': str(movie_id),
                                   'frame_number': '-1'})
    assert resp.status_code == 403
    r = resp.get_json()

    # Check for getting by frame_number
    # should produce a redirect
    logging.debug("test_movie_extract1: point2")
    resp = client.post('/api/get-frame',
                           data = {'api_key': api_key,
                                   'movie_id': str(movie_id),
                                   'frame_number': '0' })
    assert resp.status_code == 302

    # Since we got a frame, we should now be able to get a frame URN
    # urn = bottle_api.api_get_frame_urn(movie_id=movie_id, frame_number=0)
    # assert urn.startswith('s3:/') or urn.startswith('db:/')

def test_movie_extract2(client, new_movie):
    """Try extracting individual movie frames"""
    cfg = copy.copy(new_movie)
    movie_id = cfg[MOVIE_ID]
    movie_title = cfg[MOVIE_TITLE]
    api_key = cfg[API_KEY]
    user_id = cfg[USER_ID]

    movie_data = db.get_movie_data(movie_id = movie_id)
    assert filetype.guess(movie_data).mime==MIME.MP4

    # Grab three frames with the tracker and make sure they are different
    def get_movie_data_jpeg(frame_number):
        data =  tracker.extract_frame(movie_data=movie_data,frame_number=frame_number,fmt='jpeg')
        logging.debug("len(data)=%s",len(data))
        assert filetype.guess(data).mime==MIME.JPEG
        return data

    frame0 = get_movie_data_jpeg(0)
    frame1 = get_movie_data_jpeg(1)
    frame2 = get_movie_data_jpeg(2)

    assert frame0 != frame1 != frame2

    # Grab three frames with the API and see if they are different
    def get_jpeg_frame_redirect(number):
        resp = client.post('/api/get-frame',
                               data = {'api_key': api_key,
                                       'movie_id': str(movie_id),
                                       'frame_number': str(number) })
        assert resp.status_code==302
        assert resp.location is not None
        return resp.location

    jpeg0_url = get_jpeg_frame_redirect(0)
    jpeg1_url = get_jpeg_frame_redirect(1)
    jpeg2_url = get_jpeg_frame_redirect(2)
    assert jpeg0_url != jpeg1_url != jpeg2_url

    # TODO - get the data and check?



def test_log_search_movie(new_movie):
    cfg        = copy.copy(new_movie)
    api_key    = cfg[API_KEY]
    movie_id   = cfg[MOVIE_ID]
    movie_title= cfg[MOVIE_TITLE]

    dbreader = get_dbreader()
    res = dbfile.DBMySQL.csfr(dbreader, "select user_id from movies where id=%s", (movie_id,))
    user_id = res[0][0]
    res = db.get_logs( user_id=user_id, movie_id = movie_id)
    logging.info("log entries for movie:")
    for r in res:
        logging.info("%s",r)
