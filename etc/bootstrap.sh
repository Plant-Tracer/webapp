#!/usr/bin/env bash
###
### bootstrap.sh is run by the EC2 instance at startup.
### See $ROOT/template.yaml for details
###

set -euo pipefail
echo Setting up ubuntu 24.04 running in AWS for PlantTracer.
export ROOT=/opt/webapp
cd $ROOT

## Get my region
if [ -f /etc/environment.d/10-planttracer.conf ]; then
    source /etc/environment.d/10-planttracer.conf
fi

if [ -z "${AWS_REGION+x}" ]; then
    TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")
    AWS_REGION=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" -s http://169.254.169.254/latest/meta-data/placement/region)
    echo AWS_REGION=$AWS_REGION | sudo tee -a /etc/environment.d/10-planttracer.conf
fi

export AWS_REGION
export DOMAIN
export DYNAMODB_TABLE_PREFIX
export HOSTNAME
export LOG_LEVEL
export PLANTTRACER_S3_BUCKET

## Install nginx and the TLS certificate
sudo hostnamectl hostname $HOSTNAME.$DOMAIN
sudo apt -y install nginx
sudo apt -y install certbot python3-certbot-nginx

## Add the TLS certificate
if [ ! -r /etc/letsencrypt/renewal/$HOSTNAME.$DOMAIN ]; then
    sudo certbot --non-interactive --nginx --expand --cert-name $HOSTNAME.$DOMAIN \
         -d $HOST.$DOMAIN \
         --email plantadmin@planttracer.com --no-eff-email --agree-tos
fi

# Patch nginx
sudo python3 $ROOT/etc/patcher.py /etc/nginx/sites-available/default $ROOT/etc/nginx-patch $HOSTNAME.$DOMAIN --flag planttracer-nginx-patch --count 8

## First we install a functioning release and make sure that we can test it
## Note that the test will be done with the live Lambda database and S3
## and not with DynamoDBLocal

make install-ubuntu
