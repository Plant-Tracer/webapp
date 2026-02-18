Environment Variables
=====================

See https://docs.aws.amazon.com/cli/v1/userguide/cli-configure-envvars.html. Also:



Required
--------

`DYNAMODB_TABLE_PREFIX` - The prefix to add to all DynamoDB tables.

* This is required because the table namespace is top-level within an AWS account; unlike SQL, there is no higher-level *DATABASE* namespace.

* For testing, a random prefix is created, tables are created with this prefix, and the tables are deleted if the tests conclude successfully.

Optional for Demo Mode
----------------------
`DEMO_COURSE_ID` - Run in demo mode with this course. The Makefile creates a demo course called `demo`.

`DEMO_DYNAMODB_PREFIX` - Use tables with this prefix. The Makefile creates tables with a prefix `demo`.

`DEMO_USER_EMAIL` - Identifies the demo user. The Makefile creates a user with the email `demo@planttracer.com`.

Optional for using AWS
----------------------
Region selection:

`AWS_REGION` - The AWS region you are using.

`AWS_PROFILE` - Which profile in the `$HOME/.aws/credentials` and `$HOME/.aws/config` the webapp will use.

Optional for sending mail
-------------------------
`PLANTTRACER_CREDENTIALS` - A configuration file that has email credentials


Optional for Local Development
------------------------------

`AWS_REGION` - The AWS region you are using.

`AWS_PROFILE` - Which profile in the `$HOME/.aws/credentials` the webapp will use. Should be `minio` when using minio (assuming profile is installed)

`AWS_ENDPOINT_URL_DYNAMODB` - For local development, this must be set to the localhost and the port on which **DynamoDBlocal** is listening. It is typically `http://localhost:8000`.

`AWS_ENDPOINT_URL_S3` - For local development, this must be set to the localhost and the port on which **minIO** is listening. It is typically `http://localhost:9000`.


For local usage:

* Minio - If you are using minio, either `AWS_PROFILE` should be `minio` (and the minio profile should be installed) or both `AWS_ACCESS_KEY_ID` and `AWS_SECRET_KEY` should be `minioadmin`.
