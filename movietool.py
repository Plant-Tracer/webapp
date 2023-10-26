"""
Movie tool

"""

import sys
import os
import configparser
import json
import tempfile
import re
import time

import uuid
import pymysql
import logging
import subprocess

from tabulate import tabulate

# pylint: disable=no-member

import db
from paths import TEMPLATE_DIR, SCHEMA_FILE
from lib.ctools import clogging
from lib.ctools import dbfile

ROOT_USER = 0

__version__ = '0.0.1'

FFMPEG = 'ffmpeg'

MOVIE_SPLIT_TIMEOUT=60
DEFAULT_FPS = 20

def extract(auth, *, movie_id, user_id):
    """Download movie_id to a temporary file, extract all of the frames, and upload to the frames database.
    Does not run if frames are already in the database
    :return: count = number of frames uploaded.
    """
    info = db.movie_frames_info(movie_id=movie_id)
    if info['count']!=0:
        raise RuntimeError(f"extract movie frames requires no frames for movie {movie_id}; frame count {info['count']}")

    metadata = db.get_movie_metadata(user_id=user_id, movie_id=movie_id)
    logging.info("Movie %s metadata: %s",movie_id, metadata)

    count  = 0
    with tempfile.NamedTemporaryFile(mode='ab') as tf:
        data = db.get_movie_data(movie_id=movie_id)
        logging.info("tempfile %s  movie size: %s written",tf.name,len(data))
        tf.write(data)
        tf.flush()

        with tempfile.TemporaryDirectory() as td:
            template = os.path.join(td,"frame_%04d.jpg")

            proc = subprocess.Popen([FFMPEG,'-i',tf.name,template], stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf-8')
            try:
                (stdout,stderr) = proc.communicate(timeout=MOVIE_SPLIT_TIMEOUT)
                logging.info("stdout = %s",stdout.replace("\n","\\n"))
                logging.info("stderr = %s",stderr.replace("\n","\\n"))
            except TimeoutExpired:
                proc.kill()
                (stdout,stderr) = proc.communicate()
                logging.error("stdout = %s",stdout.replace("\n","\\n"))
                logging.error("stderr = %s",stderr.replace("\n","\\n"))

            # Find the FPS and the duration
            m = re.search(r"Duration: (\d\d):(\d\d):(\d\d\.\d\d)",stderr, re.MULTILINE)
            if m:
                duration = int(m.group(1))*3600 + int(m.group(2))*60 + float(m.group(3))
                logging.info("hms=%s:%s:%s duration=%s", m.group(1), m.group(2), m.group(3), duration)
            else:
                duration = None
            m = re.search(r", (\d+) fps",stderr, re.MULTILINE)
            if m:
                logging.info("fps=%s", m.group(1))
                fps = int( m.group(1))
            else:
                fps = DEFAULT_FPS

            # Now upload each frame. Note that ffmpeg starts with frame 1, so we need to adjust.
            for frame in range(1,10000):
                fname = template % frame;
                if os.path.exists(fname):
                    frame_msec = ((frame-1) * 1000) // DEFAULT_FPS
                    prev_frame_id = None
                    with open(fname,"rb") as f:
                        frame_data = f.read()
                        logging.info("uploading movie_id=%s frame=%s msec=%s", movie_id, frame, frame_msec)
                        t0 = time.time()
                        frame_id = db.create_new_frame(movie_id=movie_id, frame_msec=frame_msec, frame_data=frame_data)
                        t1 = time.time()
                        assert frame_id != prev_frame_id
                        prev_frame_id = frame_id
                        logging.info("uploaded. frame_id=%s time to upload=%d", frame_id, t1-t0)
                        count += 1
    logging.info("Frames extracted: %s",count)
    return count





if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Work with movies in the database",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    required = parser.add_argument_group('required arguments')

    required.add_argument(
        "--rootconfig",
        help='specify config file with MySQL database root credentials in [client] section. Format is the same as the mysql --defaults-extra-file= argument', required=True)
    parser.add_argument( "--list",  help="List all the movies", action='store_true')
    parser.add_argument( "--extract",  help="extract all of the frames for the given movie", type=int)
    parser.add_argument( "--purgeframes", help="purge the frames associated with a movie", type=int)

    clogging.add_argument(parser, loglevel_default='WARNING')
    args = parser.parse_args()
    clogging.setup(level=args.loglevel)

    auth = dbfile.DBMySQLAuth.FromConfigFile(args.rootconfig, 'dbwriter')
    try:
        d = dbfile.DBMySQL(auth)
    except pymysql.err.OperationalError:
        print("Invalid auth: ", auth, file=sys.stderr)
        raise

    if args.list:
        rows = [(item['movie_id'],item['title']) for item in db.list_movies(0)]
        print(tabulate(rows, headers=['movie_id','title']))

    if args.purgeframes:
        db.purge_movie_frames(movie_id=args.purgeframes)

    if args.extract:
        count = extract(auth, movie_id=args.extract, user_id=ROOT_USER)
        print("Frames extracted:",count)
