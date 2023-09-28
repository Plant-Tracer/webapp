from PIL import Image
import blocktrack
from paths import TEST_DATA_DIR
import pytest
import sys
import os
import bottle
import logging
import json
import tempfile
import glob

from os.path import abspath, dirname

# https://bottlepy.org/docs/dev/recipes.html#unit-testing-bottle-applications

import subprocess
from boddle import boddle

sys.path.append(dirname(dirname(abspath(__file__))))

import bottle_app

# get the first MOV
TEST_MOV = glob.glob(os.path.join(TEST_DATA_DIR, '*.mov'))[0]


# https://superuser.com/questions/984850/linux-how-to-extract-frames-from-a-video-lossless
def extract_all_frames(infilename, pattern, destdir):
    ffmpeg_cmd = ['ffmpeg', '-i', infilename,
                  os.path.join(destdir, pattern), '-hide_banner']
    logging.info(ffmpeg_cmd)
    ret = subprocess.call(ffmpeg_cmd)
    if ret > 0:
        raise RuntimeError("failed: "+ffmpeg_cmd.join(' '))


PATTERN = 'frame_%05d.jpeg'


def test_blocktrack():
    count = 0
    with tempfile.TemporaryDirectory() as td:
        extract_all_frames(TEST_MOV, PATTERN, td)
        context = None
        for fn in sorted(glob.glob(os.path.join(td, "*.jpeg"))):
            logging.info("process %s", fn)
            with open(fn, 'rb') as infile:
                img = Image.open(infile)
                context = blocktrack.blocktrack(context, img)
                count += 1
            logging.info("frame %d output: %s", count, context)
    logging.info("total frames processed: %d", count)
    if count == 0:
        raise RuntimeError("no frames processed")
