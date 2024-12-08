Notes on Deploying to SAM
=========================

* https://docs.aws.amazon.com/lambda/latest/dg/python-handler.html
* https://github.com/tzelleke/aws-sam-fastapi

`sam build` takes what's in the requirements.txt file, installs it into the directory `.aws-sam/build/HandlerFunction`, makes it into a
ZIP file, and uploads the ZIP file to S3.  The ZIP file needs to be unzipped when the lambda does a cold-start.

Docker
------

Normal SAM is limited to 512MiB. The only way around this is by using Docker containers.

I had no problem building and deploying a Lambda function with a Docker Container from EC2. However, from my mac, I could not build the container, even when Docker was installed.

I was able to run x86 AWS Linux on my M1 Mac using Docker:

Dockerfile:

```
FROM amazonlinux:latest

RUN yum install -y shadow-utils sudo && \
    useradd -m ec2-user && \
    echo "ec2-user ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

USER ec2-user
WORKDIR /home/ec2-user
```

Makefile:
```
build:
	echo build an x86 aws linux container with an ec2-user account
	docker build -t amazonlinux-ec2 .
	docker run --platform linux/amd64 -it amazonlinux-ec2 bash
```

I haven't yet tried running SAM inside the docker container


--- To make things somewhat faster, it's preferable to create a Layer which has the big files in it (opencv, numpy, etc).

The layer is defined in the template.yaml file. Here it is in the directory `layer/`. Inside that is `layer/python/requirements.txt` which contains the referenced python files to be installed in the layer by `sam build`.  Ideally the layer doesn't change much, so it doesn't need to be uploaded much.

Virtual Environment
-------------------

For local debugging, we install the files in both `requirements.txt`
and `layer/python/requirements.txt` into the virtual environment. The deployed runtime doesn't use a virtual environment.

Size
----
We are limited to 256MiB on lambda functions. One way around this is by using Docker containers. But another way is to delay the loading of ffmpeg to the times that we need it, and not having it always load.

Commands to try:
----------------

`sam sync --stack-name planttracer-webapp`
* Sends changes to the server

`sam logs planttracer-app --tail`
* Watches for logfile changes

`sam logs planttracer-app -s"5min ago"`
* Prints all logs from last 5 minutes

`sam validate && sam build && sam deploy --no-confirm-changeset`
* validates, builds, and deploys without asking questions

`sam sync --stack-name planttracer-webapp --watch`
* Deploys watching your local file system; changes are reflected on the live system, but do not persist after you ^c. In testing, a change in the local file system was reflected in less than 5 seconds on the server.


Set Up:
------

Request a certificate for simson-dev.planttracer.com:

``
aws acm request-certificate \
  --domain-name simson-dev.planttracer.com \
  --validation-method DNS \
  --region us-east-1 \
  --idempotency-token simson-cert \
  --domain-validation-options DomainName=simson-dev.planttracer.com,ValidationDomain=planttracer.com
``

After requesting the certificate, retrieve the validation DNS records:
``
aws acm describe-certificate \
  --certificate-arn arn:aws:acm:us-east-1:ACCOUNT_ID:certificate/CERTIFICATE_ID \
  --region us-east-1
``

Afterwards, create the Route 53 DNS Record:
``
aws route53 change-resource-record-sets \
  --hosted-zone-id HOSTED_ZONE_ID \
  --change-batch '{
    "Changes": [
      {
        "Action": "UPSERT",
        "ResourceRecordSet": {
          "Name": "CNAME_NAME_FROM_PREVIOUS_STEP",
          "Type": "CNAME",
          "TTL": 300,
          "ResourceRecords": [
            {
              "Value": "CNAME_VALUE_FROM_PREVIOUS_STEP"
            }
          ]
        }
      }
    ]
  }'
``

Finally, verify the certificate validation:
``
aws acm describe-certificate \
  --certificate-arn arn:aws:acm:us-east-1:ACCOUNT_ID:certificate/CERTIFICATE_ID \
  --region us-east-1
``


Once the certificate is validated, you  can use its ARN in your `template.yaml` file under CertificateArn:
``
Resources:
  CustomDomainName:
    Type: AWS::ApiGatewayV2::DomainName
    Properties:
      DomainName: simson-dev.planttracer.com
      DomainNameConfigurations:
        - CertificateArn: arn:aws:acm:us-east-1:ACCOUNT_ID:certificate/CERTIFICATE_ID
          EndpointType: REGIONAL
``

Then you can bind the custom domain to the API gateway using the CLI:
``
aws apigatewayv2 create-api-mapping \
  --domain-name simson-dev.planttracer.com \
  --api-id API_ID \
  --stage-name Prod
``

Reference: https://chatgpt.com/share/674b3c8d-5b00-8010-8473-5aef2e609576

References:
-----------
* More info about Globals:
  https://github.com/awslabs/serverless-application-model/blob/master/docs/globals.rst

* More info about Function Resource:
  https://github.com/awslabs/serverless-application-model/blob/master/versions/2016-10-31.md#awsserverlessfunction

* More info about API Event Source. See:
  https://github.com/awslabs/serverless-application-model/blob/master/versions/2016-10-31.md#api
