DynamoDB and Plant Tracer
============================

The Plant Tracer webapp uses AWS DynamoDB to store:

* The user list
* The course list
* The movie list
* The per-frame annotations.

Originally this was stored in a MySQL database. We migrated to DynamoDB for cost---most uses of Plant Tracer can fit within the DynamoDB free tier, while the cost for running inside MySQL is upwards of $50/month on AWS. (Plant Tracer was originally developed using Dreamhost's free MySQL service, but that requires that you have a Dreamhost account.)

Each DynamoDB database is identified by an Account and a database name. These are specified in environment variables when the Flask application is run. For local development you can use the (AWS DynamoDB local (downloadable version))[https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/DynamoDBLocal.html]. We recommend using the version that is downloaded as a JAR file.

Amazon Linux 2023 Development Environment (EC2)
-----------------------------------------------
Thankfully, when you are running on AWS, you can use DynamoDB and S3. However:

- You need to create a DynamoDB database for use with Plant Tracer.
- You need to create an S3 bucket for use with Plant Tracer.


Schema and Naming Changes
-------------------------
Some naming changes were done for clarity and others due to name conflicts with DynamoDB's query language.

user table:
`name`  ;-> `user_name`
