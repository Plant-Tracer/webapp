"""
Movie tool

"""

import os
import os.path
import tempfile
import re
import time

import logging
import subprocess

from os.path import abspath,dirname

from tabulate import tabulate

# pylint: disable=no-member

import db
from lib.ctools import clogging

ROOT_USER = 0

__version__ = '0.0.1'

FFMPEG = 'ffmpeg'
MOVIE_SPLIT_TIMEOUT=20
DEFAULT_FPS = 20
JPEG_TEMPLATE = 'frame_%04d.jpg'

def frames_matching_template(frame_template):
    dname = dirname(abspath(frame_template))
    if not os.path.exists(dname):
        raise FileNotFoundError(dname)
    frames = []
    for ct in range(0,10000):
        fname = frame_template % ct
        if os.path.exists(fname):
            frames.append(fname)
    return frames


def upload_frames(movie_id, template, fps):
    # Now upload each frame. Note that ffmpeg starts with frame 1, so we need to adjust.

    for (ct, fname) in enumerate(frames_matching_template(template)):
        frame_msec = (ct * 1000) // fps
        prev_frame_id = None
        with open(fname,"rb") as f:
            frame_data = f.read()
        logging.info("uploading movie_id=%s fname=%s msec=%s", movie_id, fname, frame_msec)
        t0 = time.time()
        frame_id = db.create_new_frame(movie_id=movie_id, frame_msec=frame_msec, frame_data=frame_data)
        t1 = time.time()
        assert frame_id != prev_frame_id
        prev_frame_id = frame_id
        logging.info("uploaded. frame_id=%s time to upload=%d", frame_id, t1-t0)
    return ct+1


def extract_all_frames_from_file_with_ffmpeg(movie_file, output_template):
    """Extract all of the frames from a movie with ffmpeg. Returns (stdout,stderr) of the ffmpeg process."""
    if not os.path.exists(movie_file):
        raise FileNotFoundError(movie_file)
    if not os.path.exists(os.path.dirname(output_template)):
        raise FileNotFoundError(os.path.dirname(output_template))
    cmd = [FFMPEG,'-i', movie_file, output_template]
    logging.info("cmd=%s",' '.join(cmd))
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf-8') as proc:
        try:
            (stdout,stderr) = proc.communicate(timeout=MOVIE_SPLIT_TIMEOUT)
            logging.info("stdout = %s",stdout.replace("\n","\\n"))
            logging.info("stderr = %s",stderr.replace("\n","\\n"))
        except subprocess.TimeoutExpired:
            proc.kill()
            logging.error("subprocess.TimeoutExpired")
            (stdout,stderr) = proc.communicate()
            logging.error("stdout = %s",stdout.replace("\n","\\n"))
            logging.error("stderr = %s",stderr.replace("\n","\\n"))
    return (stdout, stderr)


def extract_frames(*, movie_id, user_id):
    """Download movie_id to a temporary file, extract all of the frames, and upload to the frames database.
    Does not run if frames are already in the database
    :return: count = number of frames uploaded.
    """
    info = db.movie_frames_info(movie_id=movie_id)
    if info['count']!=0:
        raise RuntimeError(f"extract movie frames requires no frames for movie {movie_id}; frame count {info['count']}")

    metadata = db.get_movie_metadata(user_id=user_id, movie_id=movie_id)
    logging.info("Movie %s metadata: %s",movie_id, metadata)

    with tempfile.NamedTemporaryFile(mode='ab') as tf:
        data = db.get_movie_data(movie_id=movie_id)
        logging.info("tempfile %s  movie size: %s written",tf.name,len(data))
        tf.write(data)
        tf.flush()

        with tempfile.TemporaryDirectory() as td:
            template = os.path.join(td, JPEG_TEMPLATE)

            (stdout,stderr) = extract_all_frames_from_file_with_ffmpeg(tf.name, template)

            # Find the FPS and the duration
            fps = DEFAULT_FPS
            duration = None
            m = re.search(r"Duration: (\d\d):(\d\d):(\d\d\.\d\d)",stderr, re.MULTILINE)
            if m:
                duration = int(m.group(1))*3600 + int(m.group(2))*60 + float(m.group(3))
                logging.info("hms=%s:%s:%s duration=%s", m.group(1), m.group(2), m.group(3), duration)
            m = re.search(r", (\d+) fps",stderr, re.MULTILINE)
            if m:
                fps = int( m.group(1))

            count = upload_frames( movie_id, template, fps)
    logging.info("Frames extracted: %s  duration: %s  fps:%s ",count, duration, fps)
    # Save  Duration and FPS to database
    return count

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Work with movies in the database",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    required = parser.add_argument_group('required arguments')

    required.add_argument(
        "--rootconfig",
        help='specify config file with MySQL database root credentials in [client] section. '
        'Format is the same as the mysql --defaults-extra-file= argument', required=True)
    parser.add_argument( "--list-movies",  help="List all the movies", action='store_true')
    parser.add_argument( "--no-frames", help="When listing all movies, just list those with no frames", action='store_true')
    parser.add_argument( "--extract",  help="extract all of the frames for the given movie and store in the frames database", type=int)
    parser.add_argument( "--extract-all",
                         help="extract all of the frames from all-movies "
                         "that do not have extracted frames for the given movie", action='store_true')
    parser.add_argument( "--purgeframes", help="purge the frames associated with a movie", type=int)

    clogging.add_argument(parser, loglevel_default='WARNING')
    args = parser.parse_args()
    clogging.setup(level=args.loglevel)

    if args.list_movies:
        rows = [(item['movie_id'],item['title']) for item in db.list_movies(0, no_frames=args.no_frames)]
        print(tabulate(rows, headers=['movie_id','title']))

    if args.purgeframes:
        db.purge_movie_frames(movie_id=args.purgeframes)

    if args.extract:
        count = extract_frames(movie_id=args.extract, user_id=ROOT_USER)
        print("Frames extracted:",count)

    if args.extract_all:
        movies_with_no_frames = [item['movie_id'] for item in db.list_movies(0, no_frames=True)]
        print("Movies with no frames:",movies_with_no_frames)
        for movie_id in movies_with_no_frames:
            extract_frames(movie_id=movie_id, user_id=ROOT_USER)
