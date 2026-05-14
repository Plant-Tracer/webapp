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
`DEMO_MODE` - Enables demo mode for this process.

`DEMO_COURSE_ID` - Identifies the course that contains the demo dataset. This does not itself enable demo mode.

`DEMO_DYNAMODB_PREFIX` - Use tables with this prefix. The Makefile creates tables with a prefix `demo`.

`DEMO_USER_EMAIL` - Identifies the demo user. The Makefile creates a user with the email `demouser@planttracer.com`.

Optional for using AWS
----------------------
Region selection:

`AWS_REGION` - The AWS region you are using.

`AWS_PROFILE` - Which profile in the `$HOME/.aws/credentials` and `$HOME/.aws/config` the webapp will use.

Optional for sending mail
-------------------------
`PLANTTRACER_CREDENTIALS` - A configuration file that has email credentials

`SMTPCONFIG_JSON` - SMTP configuration as a JSON object with keys ``SMTP_HOST``, ``SMTP_PORT``, ``SMTP_USERNAME``, ``SMTP_PASSWORD``, and optionally ``SMTP_NO_TLS`` (set to any value to disable TLS). Used for local development with Mailpit: the local Makefile sets this automatically when running with ``AWS_REGION=local``.

`MAILER_DRY_RUN` - Set to ``true`` to log email content to stderr instead of sending it. Useful for local development when no SMTP credentials or SES are configured — the magic link will appear in the Flask dev server log.


Optional for Local Development
------------------------------

`AWS_REGION` - The AWS region you are using.

`AWS_PROFILE` - Which profile in the `$HOME/.aws/credentials` the webapp will use. Should be `minio` when using minio (assuming profile is installed)

`AWS_ENDPOINT_URL_DYNAMODB` - For local development, this must be set to the localhost and the port on which **DynamoDBlocal** is listening. It is typically `http://localhost:8000`.

`AWS_ENDPOINT_URL_S3` - For local development, this must be set to the localhost and the port on which **minIO** is listening. It is typically `http://localhost:9000`.


For local usage:

* Minio - If you are using minio, either `AWS_PROFILE` should be `minio` (and the minio profile should be installed) or both `AWS_ACCESS_KEY_ID` and `AWS_SECRET_KEY` should be `minioadmin`.
