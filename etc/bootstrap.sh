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
export ADMIN_EMAIL
export COURSE_ID
export ADMIN_NAME
export COURSE_NAME
export SERVER_EMAIL

# Make $HOME/.bashrc add environment.d
if ! grep planttracer $HOME/.bashrc ; then
    echo '# source planttracer
        . "/etc/environment.d/10-planttracer.conf" && export $(cut -d= -f1 "/etc/environment.d/10-planttracer.conf" | grep -v "^#")
        ' >> ~/.bashrc
fi

## Install nginx and the TLS certificate
sudo hostnamectl set-hostname "$HOSTNAME.$DOMAIN"
sudo apt -y install nginx

## Install certbot
sudo snap install core; sudo snap refresh core
sudo snap install --classic certbot
if [ ! -e /usr/bin/certbot ]; then
    sudo ln -s /snap/bin/certbot /usr/bin/certbot
fi

# Create the Nginx reload hook
sudo mkdir -p /etc/letsencrypt/renewal-hooks/deploy/
sudo cp $ROOT/etc/reload-server.sh /etc/letsencrypt/renewal-hooks/deploy/

## Add the TLS certificate
if [ ! -d /etc/letsencrypt/renewal/$HOSTNAME.$DOMAIN ]; then
    sudo certbot --nginx --non-interactive --nginx --expand --cert-name $HOSTNAME.$DOMAIN \
         -d $HOSTNAME.$DOMAIN \
         -d $HOSTNAME-demo.$DOMAIN \
         --email plantadmin@planttracer.com --no-eff-email --agree-tos
fi

# Patch nginx
# main domain - port 5000
# demo domain - port 5100
DEFAULT=/etc/nginx/sites-available/default
echo adding $HOSTNAME.$DOMAIN to $DEFAULT
sudo python3 $ROOT/etc/patcher.py $DEFAULT $ROOT/etc/planttracer-nginx-patch $HOSTNAME.$DOMAIN \
     --flag planttracer-nginx-patch --count 8

echo Creating $ROOT/etc/planttracer-nginx-patch.5100
/bin/rm -f $ROOT/etc/planttracer-nginx-patch.5100
sed s/5000/5100/ $ROOT/etc/planttracer-nginx-patch > $ROOT/etc/planttracer-nginx-patch.5100
echo adding $HOSTNAME-demo.$DOMAIN to $DEFAULT
sudo python3 $ROOT/etc/patcher.py $DEFAULT $ROOT/etc/planttracer-nginx-patch $HOSTNAME-demo.$DOMAIN \
     --flag planttracer-nginx-patch.5100 --count 8

if ! nginx -t; then
    echo "CRITICAL: patcher.py broke the nginx config!"
    sudo mv /etc/nginx/sites-available/default.old /etc/nginx/sites-available/default
fi

sudo systemctl reload nginx

sudo cp $ROOT/etc/planttracer.service /etc/systemd/system/planttracer.service
sudo systemctl daemon-reload


## First we install a functioning release and make sure that we can test it
## Note that the test will be done with the live Lambda database and S3
## and not with DynamoDBLocal

sudo apt-get update
sudo apt-get install -y python3-pip pipx
pipx ensurepath
export PATH="$HOME/.local/bin:$PATH"

## Remove system poetry if present
sudo apt-get remove --purge -y poetry || true

## Install Poetry and ensure it is >= 1.8.0
# We use the absolute path to ensure the script doesn't rely on the current PATH
pipx install poetry --force || pipx upgrade poetry

## Verify Poetry version (should be 1.8.x or higher)
poetry --version

make install-ubuntu

## Create course if not present and send verification email to admin (idempotent)
if [ -n "${COURSE_ID:-}" ] && [ -n "${COURSE_NAME:-}" ] && [ -n "${ADMIN_EMAIL:-}" ] && [ -n "${ADMIN_NAME:-}" ]; then
    poetry run python src/dbutil.py --create_course \
        --course_id "$COURSE_ID" \
        --course_name "$COURSE_NAME" \
        --admin_email "$ADMIN_EMAIL" \
        --admin_name "$ADMIN_NAME" \
        --send-email
fi

## Create demo course, demo user (demo@planttracer.com), and demo movies for the demo host (HOSTNAME-demo.$DOMAIN, port 5100).
## Idempotent: course/user creation tolerates existing; movies are added from tests/data if present.
poetry run python src/dbutil.py --create_demos

## Start up the planttracer service
sudo systemctl daemon-reload
sudo systemctl start planttracer.service
sudo systemctl enable planttracer.service
