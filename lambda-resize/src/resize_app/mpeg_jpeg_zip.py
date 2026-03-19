"""
mpeg_jpeg_zip.py:
Routines for ripping mpegs out of jepgs and making zip files
"""

import os
import sys
import time
import uuid
import json
from decimal import Decimal
from typing import Any, Dict, Optional
import io
from PIL import Image, ImageDraw, ImageFont
import cv2
from contextlib import closing

from .src.app.odb import (
    DDBO,
    ENABLED,
    MOVIE_DATA_URN,
    MOVIE_ROTATION,
    MOVIE_MAX_WIDTH,
    MOVIE_JPEG_QUALITY,
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

def add_jpeg_comment(jpeg_bytes: bytes, comment: str) -> bytes:
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

def generate_test_jpeg(n: int) -> bytes:
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

def get_frames_frame_jpeg_from_url(url: str, rotation: int) -> Optional[bytes]:
    """
    Generator
    Fetches the first frame of a video from a URL, applies rotation,
    scales to a maximum dimension of 640px, and returns a binary JPEG.

    :param url: The presigned S3 URL (or any accessible HTTP video URL).
    :param rotation: 0, 90, 180, or 270.
    :return: yields a sequence of JPEG image as a byte array, or None if the video couldn't be read.
    """

    # 1. Read the first frame from the URL
    cap = cv2.VideoCapture(url)
    try:
        while True:
            success, frame = cap.read()
            if not success or frame is None:
                break

            # 2. Apply Rotation
            if rotation == 90:
                frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
            elif rotation == 180:
                frame = cv2.rotate(frame, cv2.ROTATE_180)
            elif rotation == 270:
                frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
            elif rotation != 0:
                raise ValueError("Rotation must be 0, 90, 180, or 270")

            # 3. Calculate scaling to make the maximum dimension 640
            h, w = frame.shape[:2]
            max_dim = max(h, w)

            if max_dim > 0:
                scale = MOVIE_MAX_WIDTH / max_dim
                new_w = int(w * scale)
                new_h = int(h * scale)

                # cv2.INTER_AREA is the best interpolation method for shrinking images
                frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)

            # 4. Encode the frame to JPEG in memory
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), MOVIE_JPEG_QUALITY]
            result, encimg = cv2.imencode('.jpg', frame, encode_param)

            if not result:
                raise ValueError("Failed to encode frame to JPEG.")

            # 5. Return the binary string
            yield encimg.tobytes()
    finally:
        # Finished. Release the handle
        cap.release()

def get_first_frame_from_url(url: str, rotation: int) -> Optional[bytes]:
    """
    Safely grabs the first frame using a context manager and a for loop.
    """
    # closing() turns the generator into a context manager
    with closing(get_frames_frame_jpeg_from_url(url, rotation)) as frame_gen:

        # The for loop elegantly yields the first item
        for frame in frame_gen:
            # We return immediately, which exits the 'with' block.
            # Python automatically calls frame_gen.close() here!
            return frame

    # If the loop never runs (video was empty/broken), it falls through to here
    return None
