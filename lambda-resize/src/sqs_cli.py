"""
Toy cli for exercising the routines.
"""

from pathlib import Path
import argparse
from resize_app import movie_glue

def do_jpeg(args):
    data = movie_glue.generate_test_jpeg(args.rotation)
    args.output.write_bytes(data)

def main():
    parser = argparse.ArgumentParser(prog='sqs_cli', description='cli tester for SQS',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    subparsers = parser.add_subparsers(dest='command', required=True)
    jpeg_parser = subparsers.add_parser('jpeg', help='Make a jpeg')
    jpeg_parser.set_defaults(func=do_jpeg)
    jpeg_parser.add_argument("rotation",type=int,default=0)
    jpeg_parser.add_argument("--output",type=Path)
    args = parser.parse_args()
    return args.func(args)


if __name__=="__main__":
    main()
