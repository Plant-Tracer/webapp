DynamoDB and Plant Tracer
============================

The Plant Tracer webapp uses AWS DynamoDB to store:

* The user list
* The course list
* The movie list
* The per-frame annotations.

Originally this was stored in a MySQL database. We migrated to DynamoDB for cost---most uses of Plant Tracer can fit within the DynamoDB free tier, while the cost for running inside MySQL is upwards of $50/month on AWS. (Plant Tracer was originally developed using Dreamhost's free MySQL service, but that requires that you have a Dreamhost account.)

Each DynamoDB database is identified by an Account and a database name. These are specified in environment variables when the Flask application is run. For local development you can use the (AWS DynamoDB local (downloadable version))[https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/DynamoDBLocal.html]. We recommend using the version that is downloaded as a JAR file.

Local Development and GitHub Actions
-----------------
For local development (and for running in GitHub Actions) the local DynamoDB database must be downloaded from AWS. This is a low-performance implementation of DynamoDB that is more than adequate for testing. Details of how to download it can be found (on the AWS website)[https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/DynamoDBLocal.DownloadingAndRunning.html]. It is downloaded and installed automatically with the `make install_local_dynamodb` target.

To run the DynamoDB, you must have JDK operational. On Linux it can be installed with `sudo apt install -y ant`. On MacOS it is installed with `brew install openjdk@17`.

The provided script `local_dynamodb_control.bash` manages starting and stopping DynamoDBLocal. It handles properly setting the `JAVA_HOME` and `PATH` environment variables under MacOS

To use the local (or the remote) DynamoDB, it is necessary to set the `AWS_ACCESS_KEY_ID`, `AWS_ACCESS_SECRET_KEY` an `AWS_DEFAULT_REGION` variables to values that are valid but that will be ignored. environment variables. For the local DynamoDB, they are ignored, although they must be valid, in that they must contain only letters (A–Z, a–z) and numbers (0–9). We recommend `plant_tracer_access` and `plant_tracer_secret`, respectively. It is also important to specify the endpoint url when accessing the server:

```
aws dynamodb list-tables --endpoint-url http://localhost:8010
```

Then you can:
```
% aws dynamodb list-tables --endpoint-url http://localhost:8010                                       (dev-dynamodb)webapp
{
    "TableNames": []
}
```

Note that we use port 8010 and not the default port of 8000, as that would be linkly to cause conflicts.

Amazon Linux 2023 Development Environment (EC2)
-----------------------------------------------
Thankfully, when you are running on AWS, you can use DynamoDB and S3. However:

- You need to create a DynamoDB database for use with Plant Tracer.
- You need to create an S3 bucket for use with Plant Tracer.
