#!/usr/bin/env bash
###
### bootstrap.sh is run by the EC2 instance at startup.
### See $ROOT/template.yaml for details
###
### Idempotent: safe to run again after 'git pull'. Ensures poetry.lock is
### current before install so pyproject.toml changes don't break the build.
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
export LAMBDA_RESIZE_ARN

# Make $HOME/.bashrc add environment.d
if ! grep planttracer $HOME/.bashrc ; then
    echo '# source planttracer
        . "/etc/environment.d/10-planttracer.conf" && export $(cut -d= -f1 "/etc/environment.d/10-planttracer.conf" | grep -v "^#")
        ' >> ~/.bashrc
fi

# Developer hints in .bash_profile (shown on login)
if ! grep -q "PlantTracer dev hints" /home/ubuntu/.bash_profile 2>/dev/null; then
    sudo tee -a /home/ubuntu/.bash_profile << 'BASHPROFILE'

# PlantTracer dev hints:
echo "  View webserver log:  journalctl -u planttracer.service -f"
echo "  Enable gunicorn auto-reload:    cd /opt/webapp && make gunicorn-reload"
echo "tail /var/log/user-data.log"
tail /var/log/user-data.log
BASHPROFILE
    sudo chown ubuntu:ubuntu /home/ubuntu/.bash_profile
fi

## Install pipx
sudo apt-get update
sudo apt-get install -y python3-pip pipx
pipx ensurepath
export PATH="$HOME/.local/bin:$PATH"

## Remove system poetry and install poetry through pipx
sudo apt-get remove --purge -y poetry || true
pipx install poetry --force || pipx upgrade poetry
poetry --version
poetry self add poetry-plugin-export

## Install nginx and the TLS certificate
sudo hostnamectl set-hostname "$HOSTNAME.$DOMAIN"
sudo apt -y install nginx

## Restore NGINX distribution configuration if we are runnng the second time
DEFAULT=/etc/nginx/sites-available/default
if [ -r $DEFAULT.dist ]; then
   sudo cp $DEFAULT.dist $DEFAULT
fi
sudo cp -f $DEFAULT $DEFAULT.dist

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
# Target "server_name" so we match the default server block (server_name _;) and replace
# the default location with our proxy. --count 4 removes the 4 lines after server_name
# (location / { try_files } }) so the server block's closing } is kept.
echo adding $HOSTNAME.$DOMAIN to $DEFAULT
sudo python3 $ROOT/etc/patcher.py $DEFAULT $ROOT/etc/planttracer-nginx-patch 'server_name' \
     --flag planttracer-nginx-patch --count 4

echo Creating $ROOT/etc/planttracer-nginx-patch.5100
/bin/rm -f $ROOT/etc/planttracer-nginx-patch.5100
sed s/5000/5100/ $ROOT/etc/planttracer-nginx-patch > $ROOT/etc/planttracer-nginx-patch.5100
echo adding $HOSTNAME-demo.$DOMAIN to $DEFAULT
sudo python3 $ROOT/etc/patcher.py $DEFAULT $ROOT/etc/planttracer-nginx-patch.5100 "$HOSTNAME-demo.$DOMAIN" \
     --flag planttracer-nginx-patch.5100 --count 4

# Run nginx -t with sudo (avoids "user" directive warning) and filter that warning from output
nginx_test_out=$(sudo /usr/sbin/nginx -t 2>&1)
nginx_exit=$?
echo "$nginx_test_out" | grep -v 'the "user" directive' 1>&2 || true
if [ "$nginx_exit" -ne 0 ]; then
    echo "CRITICAL: patcher.py broke the nginx config!"
    sudo mv /etc/nginx/sites-available/default.old /etc/nginx/sites-available/default
    exit 1
fi

sudo systemctl reload nginx

sudo cp $ROOT/etc/planttracer.service /etc/systemd/system/planttracer.service
sudo systemctl daemon-reload


## Create venv and install app deps (pyproject.toml and lock already validated above).
make install-ubuntu

## Ensure venv has all deps (Make may skip poetry install if .venv exists; re-run so second bootstrap or git pull leaves venv in sync)
poetry install

## Create demo course, demo user (demouser@planttracer.com), and demo movies for the demo host (HOSTNAME-demo.$DOMAIN, port 5100).
## Idempotent: course/user creation tolerates existing; movies are added from tests/data if present.
poetry run python src/dbutil.py --create_demos

## Apply CORS to the S3 bucket so the browser can fetch movie zip URLs from the app origin (e.g. simson2.planttracer.com).
if [ -n "${PLANTTRACER_S3_BUCKET:-}" ]; then
    poetry run python -m app.s3_presigned "$PLANTTRACER_S3_BUCKET" || true
fi

## Idempotently add S3 -> Lambda trigger for prefix uploads/ (if already present, leave as-is).
if [ -n "${PLANTTRACER_S3_BUCKET:-}" ] && [ -n "${LAMBDA_RESIZE_ARN:-}" ]; then
    poetry run python etc/s3_upload_trigger.py || true
fi

## Create course if not present and send verification email to admin (idempotent)
if [ -n "${COURSE_ID:-}" ] && [ -n "${COURSE_NAME:-}" ] && [ -n "${ADMIN_EMAIL:-}" ] && [ -n "${ADMIN_NAME:-}" ]; then
    poetry run python src/dbutil.py --create_course \
        --course_id "$COURSE_ID" \
        --course_name "$COURSE_NAME" \
        --admin_email "$ADMIN_EMAIL" \
        --admin_name "$ADMIN_NAME" \
        --send-email
fi

## Start up the planttracer service
sudo systemctl daemon-reload
sudo systemctl start planttracer.service
sudo systemctl enable planttracer.service

echo "Bootstrap complete. Web server running at https://$HOSTNAME.$DOMAIN and https://$HOSTNAME-demo.$DOMAIN"
