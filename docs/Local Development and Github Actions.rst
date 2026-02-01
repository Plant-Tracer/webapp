Local Development and GitHub Actions
====================================

For GitHub Actions, the advantages are:
* Runs self-contained at GitHub without the need for an AWS account.
* AWS account credentials do not need to be stored at GitHub


DynamoDB
--------

For local development (and for running in GitHub Actions) the local DynamoDB database must be downloaded from AWS. This is a low-performance implementation of DynamoDB that is more than adequate for testing. Details of how to download it can be found (on the AWS website)[https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/DynamoDBLocal.DownloadingAndRunning.html]. It is downloaded and installed automatically with the `make install_local_dynamodb` target.

To run the DynamoDB, you must have JDK operational. On Linux it can be installed with `sudo apt install -y ant`. On MacOS it is installed with `brew install openjdk@17`.

The provided script `local_dynamodb_control.bash` manages starting and stopping DynamoDBLocal. It handles properly setting the `JAVA_HOME` and `PATH` environment variables under MacOS

To use the local (or the remote) DynamoDB, it is necessary to set the `AWS_ACCESS_KEY_ID`, `AWS_ACCESS_SECRET_KEY` an `AWS_REGION` variables to values that are valid but that will be ignored. environment variables. For the local DynamoDB, they are ignored, although they must be valid, in that they must contain only letters (A–Z, a–z) and numbers (0–9). We recommend `plant_tracer_access` and `plant_tracer_secret`, respectively. It is also important to specify the endpoint url when accessing the server::

    aws dynamodb list-tables --endpoint-url http://localhost:8010

Then you can::

    % aws dynamodb list-tables --endpoint-url http://localhost:8010                                       (dev-dynamodb)webapp
    {
        "TableNames": []
    }

Note that we use port 8010 and not the default port of 8000, as that would be linkly to cause conflicts.

S3
--
S3 is provided with Minio, an S3 implementation that stores all objects in a local file system.
