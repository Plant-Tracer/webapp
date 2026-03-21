"""
Toy cli for exercising the routines.
"""

from pathlib import Path
import json
import argparse
import subprocess

from resize_app.src.app.schema import Trackpoint
from resize_app import tracker
from resize_app import mpeg_jpeg_zip

TEST_FILE = Path(__file__).parent.parent.parent / "tests" / "data" / "2019-07-12 circumnutation.mp4"
TEST_TRACKPOINTS = '[{"x":276,"y":172,"label":"mypoint","frame_number":0}]'

def do_jpeg(args):
    data = mpeg_jpeg_zip.generate_test_jpeg(args.rotate)
    args.output.write_bytes(data)

def do_mpeg(args):
    if args.first_frame:
        url = args.fname
        data = mpeg_jpeg_zip.get_first_frame_from_url( url, args.rotate)
        jpeg = mpeg_jpeg_zip.convert_frame_to_jpeg( data )
        jpeg = mpeg_jpeg_zip.add_jpeg_comment( jpeg, "test comment" )
        args.first_frame.write_bytes( jpeg )
        subprocess.call(['ls','-l',str(args.first_frame)])

def do_track(args):
    trackpoints = [Trackpoint(**tp) for tp in json.loads(args.trackpoints)]
    print("Tracking Trackpoints:",trackpoints)

    def tracker_callback(obj:tracker.TrackerCallbackArg):
        print(obj)

    tracker.track_movie_v2(movie_url=args.infile, frame_start=0, trackpoints=trackpoints,
                           movie_zipfile_path = args.zipfile,
                           movie_traced_path = args.movie_traced,
                           rotate=args.rotate, callback=tracker_callback,
                           comment=args.comment)

def main():
    parser = argparse.ArgumentParser(prog='sqs_cli', description='cli tester for SQS',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    subparsers = parser.add_subparsers(dest='command', required=True)
    jpeg_parser = subparsers.add_parser('jpeg', help='Make a jpeg')
    jpeg_parser.set_defaults(func=do_jpeg)
    jpeg_parser.add_argument("rotate",type=int,default=0)
    jpeg_parser.add_argument("--output",type=Path)

    mpeg_parser = subparsers.add_parser('mpeg', help='Parse an mpeg')
    mpeg_parser.set_defaults(func=do_mpeg)
    mpeg_parser.add_argument("fname", help="URL or path", type=str)
    mpeg_parser.add_argument("--rotate",type=int,default=0)
    mpeg_parser.add_argument("--zipfile",type=Path)
    mpeg_parser.add_argument("--first_frame",type=Path)

    track_parser = subparsers.add_parser("tracker", help="Tracker test. Make the zipfile and track at the same time")
    track_parser.set_defaults(func=do_track)
    track_parser.add_argument("--infile", type=Path, default=TEST_FILE)
    track_parser.add_argument("--zipfile", type=Path, default=Path("outfile.zip"))
    track_parser.add_argument("--movie_traced", type=Path, default=Path("tracked.mp4"))
    track_parser.add_argument("--trackpoints", type=str, default=TEST_TRACKPOINTS)
    track_parser.add_argument("--comment", type=str, default="test comment")
    track_parser.add_argument("--rotate",type=int,default=0)
    args = parser.parse_args()
    return args.func(args)


if __name__=="__main__":
    main()
