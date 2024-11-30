import boto3
import requests
import json

if __name__=="__main__":
    session = boto3.session.Session(profile_name='planttracer_dev')
    s3_client = session.client("s3")
    url = s3_client.generate_presigned_url( ClientMethod='get_object',
                                                 Params = {
                                                     'Bucket':'planttracermovies',
                                                     'Key':'demo.txt'},
                                                     ExpiresIn=3600)
    print("url:",url)
    r = requests.get(url)
    print("r.ok:",r.ok)
    print("r.text:",r.text)
