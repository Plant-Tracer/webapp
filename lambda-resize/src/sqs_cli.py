"""
Toy cli for exercising the routines.
"""

from pathlib import Path
import json
import argparse
import subprocess

from resize_app import movie_glue
from resize_app import mpeg_jpeg_zip

TEST_FILE = Path(__file__).parent.parent / "tests" / "data" / "2019-07-12 circumnutation.mp4"
TEST_TRACKPOINTS = json.loads('[{"x":138,"y":86,"label":"mypoint"}]')

def do_jpeg(args):
    data = mpeg_jpeg_zip.generate_test_jpeg(args.rotation)
    args.output.write_bytes(data)

def do_mpeg(args):
    if args.first_frame:
        url = args.fname
        data = mpeg_jpeg_zip.get_first_frame_from_url( url, args.rotate)
        jpeg = mpeg_jpeg_zip.convert_frame_to_jpeg( data )
        jpeg = mpeg_jpeg_zip.add_jpeg_comment( jpeg, "test comment" )
        args.first_frame.write_bytes( jpeg )
        subprocess.call(['ls','-l',str(args.first_frame)])

def do_track():
    pass

def main():
    parser = argparse.ArgumentParser(prog='sqs_cli', description='cli tester for SQS',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    subparsers = parser.add_subparsers(dest='command', required=True)
    jpeg_parser = subparsers.add_parser('jpeg', help='Make a jpeg')
    jpeg_parser.set_defaults(func=do_jpeg)
    jpeg_parser.add_argument("rotation",type=int,default=0)
    jpeg_parser.add_argument("--output",type=Path)

    mpeg_parser = subparsers.add_parser('mpeg', help='Parse an mpeg')
    mpeg_parser.set_defaults(func=do_mpeg)
    mpeg_parser.add_argument("fname", help="URL or path", type=str)
    mpeg_parser.add_argument("--rotate",type=int,default=0)
    mpeg_parser.add_argument("--zipfile",type=Path)
    mpeg_parser.add_argument("--first_frame",type=Path)

    track_parser = subparsers.add_parser("tracker", help="Tracker test. Make the zipfile and track at the same time")
    track_parser.set_defaults(func=do_track)
    args = parser.parse_args()
    return args.func(args)


if __name__=="__main__":
    main()
