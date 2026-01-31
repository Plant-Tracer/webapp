#!/usr/bin/env bash
###
### bootstrap.sh is run by the EC2 instance at startup.
### See $ROOT/template.yaml for details
###

set -euo pipefail
echo Setting up ubuntu 24.04 running in AWS for PlantTracer.
export ROOT=/opt/webapp
cd $ROOT

## First we install a functioning release and make sure that we can test it
## Note that the test will be done with the live Lambda database and S3
## and not with DynamoDBLocal

make install-ubuntu
source /etc/environment.d/10-planttracer.conf
export LOG_LEVEL
export DYNAMODB_TABLE_PREFIX
export PLANTTRACER_S3_BUCKET
