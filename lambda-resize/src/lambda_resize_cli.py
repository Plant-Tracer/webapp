"""Developer diagnostics for lambda-resize image, video, and tracing code."""

import argparse
import json
from pathlib import Path

from resize_app import mpeg_jpeg_zip, tracer
from resize_app.src.app.schema import Trackpoint

TEST_FILE = Path(__file__).parents[2] / "tests" / "data" / "2019-07-12 circumnutation.mp4"
TEST_TRACKPOINTS = '[{"x":276,"y":172,"label":"mypoint","frame_number":0}]'


def make_jpeg(args):
    """Write a generated test JPEG."""
    args.output.write_bytes(mpeg_jpeg_zip.generate_test_jpeg(args.rotate))


def extract_first_frame(args):
    """Write the first movie frame as a commented JPEG."""
    frame = mpeg_jpeg_zip.get_first_frame_from_url(args.input, args.rotate)
    jpeg = mpeg_jpeg_zip.convert_frame_to_jpeg(frame)
    args.output.write_bytes(mpeg_jpeg_zip.add_jpeg_comment(jpeg, "test comment"))


def print_progress(progress):
    """Print one tracing-progress update."""
    print(progress)


def trace_movie(args):
    """Trace a movie directly without DynamoDB or S3."""
    trackpoints = [Trackpoint(**item) for item in json.loads(args.trackpoints)]
    tracer.trace_movie_v2(
        movie_url=args.infile,
        frame_start=0,
        trackpoints=trackpoints,
        movie_zipfile_path=args.zipfile,
        movie_traced_path=args.movie_traced,
        rotation=args.rotate,
        callback=print_progress,
        comment=args.comment,
    )


def build_parser():
    """Return the lambda-resize diagnostics parser."""
    parser = argparse.ArgumentParser(
        prog="lambda-resize-cli",
        description="Exercise lambda-resize media routines locally",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    jpeg_parser = subparsers.add_parser("jpeg", help="Generate a test JPEG")
    jpeg_parser.set_defaults(func=make_jpeg)
    jpeg_parser.add_argument("rotate", type=int)
    jpeg_parser.add_argument("--output", type=Path, required=True)

    frame_parser = subparsers.add_parser("first-frame", help="Extract a movie's first frame")
    frame_parser.set_defaults(func=extract_first_frame)
    frame_parser.add_argument("input", help="Movie URL or path")
    frame_parser.add_argument("--rotate", type=int, default=0)
    frame_parser.add_argument("--output", type=Path, required=True)

    trace_parser = subparsers.add_parser("tracer", help="Trace a movie and create artifacts")
    trace_parser.set_defaults(func=trace_movie)
    trace_parser.add_argument("--infile", type=Path, default=TEST_FILE)
    trace_parser.add_argument("--zipfile", type=Path, default=Path("outfile.zip"))
    trace_parser.add_argument("--movie-traced", type=Path, default=Path("tracked.mp4"))
    trace_parser.add_argument("--trackpoints", default=TEST_TRACKPOINTS)
    trace_parser.add_argument("--comment", default="test comment")
    trace_parser.add_argument("--rotate", type=int, default=0)
    return parser


def main():
    """Run the selected diagnostic."""
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
