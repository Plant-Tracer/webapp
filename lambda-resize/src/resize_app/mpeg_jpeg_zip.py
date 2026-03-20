"""
mpeg_jpeg_zip.py:
Routines for ripping mpegs out of jepgs and making zip files
"""

import tempfile
import os
import zipfile
import sys
import time
import uuid
import json
from decimal import Decimal
from typing import Any, Dict, Optional, TypeAlias,Generator
import io
from PIL import Image, ImageDraw, ImageFont
import cv2
from contextlib import closing
import numpy as np
from PIL import Image


from .src.app.constants import C
from .src.app.odb import (
    DDBO,
    ENABLED,
    MOVIE_DATA_URN,
    MOVIE_ROTATION,
    TOTAL_BYTES,
    FPS,
    WIDTH,
    HEIGHT,
    TOTAL_FRAMES,
    USER_ID,
)

from botocore.exceptions import ClientError
from aws_lambda_powertools.event_handler import Response
from aws_lambda_powertools import Logger

# Just a label for clarity
Jpeg: TypeAlias = bytes
ImgArray: TypeAlias = np.ndarray


################################################################
## jpeg generation

def generate_test_jpeg(n: int) -> Jpeg:
    """
    Generates a red 640x480 rectangle with centered text,
    rotates it by n degrees, and returns it as a binary JPEG string.
    """
    # 1. Create the base 640x480 red image
    img = Image.new('RGB', (640, 480), color='red')
    draw = ImageDraw.Draw(img)

    text = f"red rectangle rotated {n}º"

    font = ImageFont.load_default(size=24)

    # 3. Calculate text bounding box to perfectly center it
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    x = (640 - text_width) / 2
    y = (480 - text_height) / 2

    # Draw the text (using white for contrast against the red background)
    draw.text((x, y), text, font=font, fill='white')

    # 4. Rotate the image
    # expand=True resizes the canvas, changing 640x480 to 480x640 for 90/270 degrees
    if n != 0:
        img = img.rotate(n, expand=True)

    # 5. Compress to JPEG and return the binary string
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='JPEG', quality=85)

    return img_byte_arr.getvalue()

################################################################
## jpeg analysis
##

def add_jpeg_comment(jpeg_bytes: Jpeg, comment: str) -> Jpeg:
    """
    Safely injects a standard JPEG COM (Comment) segment into a JPEG byte array.
    """
    # Ensure it's actually a JPEG (starts with FF D8)
    if not jpeg_bytes.startswith(b'\xff\xd8'):
        return jpeg_bytes

    # Convert the string to bytes
    comment_bytes = comment.encode('utf-8')

    # A JPEG segment length includes the 2 bytes for the length field itself.
    # The max length of a JPEG segment is 65535 bytes.
    segment_length = len(comment_bytes) + 2
    if segment_length > 65535:
        comment_bytes = comment_bytes[:65533]
        segment_length = 65535

    # Build the COM segment:
    # Marker (0xFF 0xFE) + Length (2 bytes, big-endian) + Comment Bytes
    com_segment = b'\xff\xfe' + segment_length.to_bytes(2, byteorder='big') + comment_bytes

    # Slice the original array: [Start Marker] + [Comment Segment] + [Rest of Image]
    return jpeg_bytes[:2] + com_segment + jpeg_bytes[2:]

def convert_frame_to_jpeg( img:ImgArray, quality=90 ):
    """Use CV2 to convert a frame to a jpeg"""
    success, jpg_img = cv2.imencode('.jpg', img, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not success:
        raise ValueError("could not encode image")
    return jpg_img.tobytes()


def get_jpeg_dimensions( jpeg_bytes:Jpeg ):
    """Return (width, height) of a JPEG image, or None if decode fails."""
    arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return None
    h, w = img.shape[:2]
    return (w, h)

def resize_jpeg_to_fit( jpeg_bytes:Jpeg, max_width:int, max_height:int, quality=90):
    """Resize JPEG bytes to fit inside (max_width, max_height), preserving aspect. Returns JPEG bytes."""
    arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return jpeg_bytes
    h, w = img.shape[:2]
    if w <= max_width and h <= max_height:
        return jpeg_bytes
    scale = min(max_width / w, max_height / h)
    new_w = int(round(w * scale))
    new_h = int(round(h * scale))
    resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)
    success, jpg_img = cv2.imencode('.jpg', resized, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not success:
        raise ValueError()
    return jpg_img.tobytes()


################################################################
## cv2 mov handling
##

def extract_movie_metadata(*, movie_path:str, get_frame_count=True):
    """Use OpenCV to get movie metadata from a local file path.
    Width, height, fps and usually frame count come from container/stream metadata.
    Only if frame count is missing do we fall back to counting frames."""
    cap = cv2.VideoCapture(movie_path)
    try:
        width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        fps    = cap.get(cv2.CAP_PROP_FPS)
        frame_count = None
        if get_frame_count:
            frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            if frame_count is not None and frame_count > 0:
                frame_count = int(frame_count)
            else:
                frame_count = 0
                while True:
                    ret, frame = cap.read()
                    if not ret:
                        break
                    if len(frame) == 0:
                        raise ValueError("corrupt movie frame")
                    frame_count += 1
        if os.path.exists(movie_path):
            total_bytes = os.path.getsize(movie_path)
        else:
            total_bytes = None
        return {
            'total_frames': frame_count,
            'total_bytes': total_bytes,
            'width': width,
            'height': height,
            'fps': fps,
        }
    finally:
        cap.release()


def extract_frame(*, movie_data, frame_number, fmt):
    """Extract a single frame from movie data using CV2. This is not an efficient approach to read the entire movie.
    Perhaps  make frame_number an array of frames to allow multiple frames to be extracted, with a callback?
    :param: movie_data - binary object of data
    :param: frame_number - frame to extract
    :param: fmt - format wanted. CV2-return a CV2 image; 'jpeg' - return a jpeg image as a byte array.
    """
    assert fmt in ['CV2', 'jpeg']
    assert movie_data is not None
    # CV2's VideoCapture method does not support reading from a memory buffer.
    # So perhaps we will change this to use a named pipe
    with tempfile.NamedTemporaryFile(mode='ab') as tf:
        tf.write(movie_data)
        tf.flush()
        cap = cv2.VideoCapture(tf.name)

    # skip to frame_number (first frame is #0)
    for _ in range(frame_number + 1):
        ret, frame = cap.read()
        if not ret:
            raise ValueError(f"invalid frame_number {frame_number}")
        match fmt:
            case 'CV2':
                return frame
            case 'jpeg':
                return convert_frame_to_jpeg(frame)
            case _:
                raise ValueError("Invalid fmt: " + fmt)
    raise ValueError(f"invalid frame_number {frame_number}")


def get_frames_from_url(url: str, rotate: int) -> Generator[Any, None, None]:
    """
    Generator
    Fetches the first frame of a video from a URL, applies rotate,
    scales to a maximum dimension of 640px, and returns a binary JPEG.

    :param url: The presigned S3 URL (or any accessible HTTP video URL).
    :param rotate: 0, 90, 180, or 270.
    :yield: OpenCV image frames (ndarray)
    """

    # 1. Read the first frame from the URL
    cap = cv2.VideoCapture(url)
    try:
        while True:
            success, frame = cap.read()
            if not success or frame is None:
                break

            # 2. Apply Rotate
            if rotate == 90:
                frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
            elif rotate == 180:
                frame = cv2.rotate(frame, cv2.ROTATE_180)
            elif rotate == 270:
                frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
            elif rotate != 0:
                raise ValueError("Rotate must be 0, 90, 180, or 270")

            # 3. Calculate scaling to make the maximum dimension 640
            h, w = frame.shape[:2]
            max_dim = max(h, w)

            if max_dim > 0:
                scale = C.MOVIE_MAX_WIDTH / max_dim
                new_w = int(w * scale)
                new_h = int(h * scale)
                frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)

            yield frame
    finally:
        # Finished. Release the handle
        cap.release()



def get_first_frame_from_url(url: str, rotate: int) -> Optional[bytes]:
    """
    Safely grabs the first frame using a context manager and a for loop.
    """
    # closing() turns the generator into a context manager
    with closing(get_frames_from_url(url, rotate)) as frame_gen:

        # The for loop elegantly yields the first item
        print("frame_gen:",frame_gen)
        for frame in frame_gen:
            # We return immediately, which exits the 'with' block.
            # Python automatically calls frame_gen.close() here!
            return frame

    # If the loop never runs (video was empty/broken), it falls through to here
    return None
