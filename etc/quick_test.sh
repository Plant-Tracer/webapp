#!/bin/bash
source /etc/environment.d/10-planttracer.conf
export LOG_LEVEL
export DYNAMODB_TABLE_PREFIX
export PLANTTRACER_S3_BUCKET
export AWS_REGION
cd /opt/webapp
poetry run python -c 'import src.app.odb as odb; print(odb.DDBO());'
