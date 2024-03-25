"""
MWE to generate a signed post and then upload a file
"""

# https://docs.aws.amazon.com/AmazonS3/latest/userguide/example_s3_Scenario_PresignedUrl_section.html
# https://stackoverflow.com/questions/34348639/amazon-aws-s3-browser-based-upload-using-post
# https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3/client/generate_presigned_post.html
# But it finally took GPT-4 to tell me I also needed to specify Conditions

# Always go to the boto3 documentation:
# https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html

import boto3
import requests
import json


if __name__=="__main__":
    session = boto3.session.Session(profile_name='planttracer_dev')
    s3_client = session.client("s3")
    response = s3_client.generate_presigned_post( Bucket="planttracermovies",
                                                  Key="demo.txt",
                                                  Conditions=[
                                                      {"Content-Type": "text/plain"},          # Explicitly allow Content-Type header
                                                      ["content-length-range", 1, 10485760],  # Example condition: limit size between 1 and 10 MB
                                                  ],
                                                  Fields= {
                                                      'Content-Type':'text/plain'
                                                  },
                                                  ExpiresIn=3600)
    print("response:",json.dumps(response,indent=4,default=str))


    with open("demo.txt","rb") as f:
        r = requests.post(response['url'],
                                 files={'file':f},
                                 data=response['fields'])
    if r.ok:
        print("file uploaded successfully.")
    print("response:",r.status_code)
    print(r.text)
