This directory is for aws-sam.

Key files:
- `template.yaml` - this is the AWS SAM template that does the magic
- `samconfig.yaml` - This records the parameters and other functions
  that change with a deployment.  It does not need to be put into
  version control.
- `Makefile` - contains a bunch of targets for people who can't
  remember the AWS `sam` commands.


Environment variables that you should know about/set:

|Variable|Meaning|
|--------------|-------------|
|`AWS_PROFILE` | The profile that you are using (in $HOME/.aws/config) |
|`AWS_REGION`  | The region you are deploying to. Set to `local` for testing locally with minio and dynamoDBLocal|
|`STACK`       | The name of the stack that you are deploying to. Must be unique in your AWS account |
|`STACK_STAGE` | This is legacy, when we actually had a staging stack. Now you stage by just deploying to a different stack name |
|`DYNAMODB_TABLE_PREFIX` | The prefix for your DynamoDB Table Names. Must be unique in your AWS account.|

launch with:

```
AWS_PROFILE=plantadmin AWS_REGION=us-east-1 make sam-deploy-guided
```
Note: do not deploy using the AWS account root user. Configure and use a least-privilege IAM role or an AWS IAM Identity Center–provisioned identity (referenced by the `AWS_PROFILE` above) with only the permissions required to deploy this stack.

You must have docker or finch installed and running (I'm recommending finch).

# Core Functionality
AWS SAM template that uses cloud formations to:
- Create a new VM
- Create the necessary DynamoDB tables all with the given prefix.
- Create a lambda function that watches the S3 bucket in the /uploads
  prefix, resizes as necessary, and moves the object to the correct location.

## The created VM

## The Created Lambda Function

Core functionality:
- Watches AWS S3. When a movie is uploaded:
  - Process (see below)
- Accepts resize requests with an S3 URL
  - Process
- Process an AWS URL:
  - Check for version number metadata. If present, stop
  - Resize if necessary
  - Add to DynamoDB if not already present
  - Add metadata 'processed' with version
  - Resize if necessary
  - Add to DynamoDB if not already present
- Maintains a log of actions in {prefix}-logs table
- Get log entries (does it need authentication? Not right now)


Resize code base:
- AWS SAM, modeled on https://github.com/Harvard-CSCI-E-11/spring26/tree/main/etc/e11-cli/lambda-home
- lambda function serves as API endpoints
- HTTP access point
- ../src/app/* vended into app/src as necessary


# Data Management

Movies:
------
- Every movie has its mpeg file, its zipfile, and its `keyframe`. Eachg are stored at predictable locations:
  - movie: course_id/movie_id.mpeg
  - zipfile:  course_id/movie_id.zip
  - keyframe: course_id/movie_id.keyframe.jpeg


Movie Metadata
--------------
We use the x-planttracer: metadata tag to determine if a movie has been procesed or not.

To read:
```
import boto3

s3 = boto3.client('s3')
resp = s3.head_object(Bucket='my-bucket', Key='my-key')
print(resp['Metadata'].get('x-planttracer'))
```

To update to a current image, you must do a self-copy:
```
import boto3

s3 = boto3.client('s3')

bucket = 'my-bucket'
key = 'my-key'

# Get existing metadata (optional, to preserve it)
head = s3.head_object(Bucket=bucket, Key=key)
metadata = head['Metadata']
metadata['x-planttracer'] = 'true'  # Add or update your custom field

# Copy object onto itself with replaced metadata
s3.copy_object(
    Bucket=bucket,
    Key=key,
    CopySource={'Bucket': bucket, 'Key': key},
    Metadata=metadata,
    MetadataDirective='REPLACE'
)
```

When writing it new:
```
import boto3

s3 = boto3.client('s3')

bucket = 'my-bucket'
key = 'my-key'
buf = b'some binary data'

s3.put_object(
    Bucket=bucket,
    Key=key,
    Body=buf,
    Metadata={
        'x-planttracer': 'true'
    },
    ContentType='application/octet-stream'
)
```


# Configuring your developer machine
You will need to install the Session Manager Plugin for the AWS CLI.
MacOS:
```
brew install --cask session-manager-plugin
```

Windows:
```
Start-BitsTransfer -Source "https://s3.amazonaws.com/session-manager-downloads/plugin/latest/windows/SessionManagerPluginSetup.exe" -Destination "$env:USERPROFILE\Downloads\SessionManagerPluginSetup.exe"

Start-Process "$env:USERPROFILE\Downloads\SessionManagerPluginSetup.exe" -ArgumentList "/install" -Wait
```

Linux:
```
curl "https://s3.amazonaws.com/session-manager-downloads/plugin/latest/ubuntu_64bit/session-manager-plugin.deb" -o "session-manager-plugin.deb"
sudo dpkg -i session-manager-plugin.deb
```
## Accessing the server:
```
AWS_PROFILE=planttracer aws ssm start-session --target i-002f7d7909fd08e31
AWS_PROFILE=planttracer aws ec2-instance-connect ssh --os-user ubuntu --instance-id i-002f7d7909fd08e31 --extra-args '-o IdentitiesOnly=yes'
```

## Bootstrap
* `/var/lib/cloud/instance/user-data.txt` - contains original bootstrap program.

Find logs in:
* `/var/log/cloud-init.log`
* `/var/log/cloud-init-output.log`

# Local Variables:
# fill-column: 150
# End:
