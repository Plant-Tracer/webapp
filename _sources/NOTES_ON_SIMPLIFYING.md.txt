- sha256 not needed for uploading
- no need to support objects stored in MySQL databsae: make everything be stored in S3.
- no need to cache anything in memory, just get the objects to/from objectdb.

Deploying SAM to a private domain:
https://rhuaridh.co.uk/blog/aws-sam-custom-domain.html
