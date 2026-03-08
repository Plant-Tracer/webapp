#!/usr/bin/env bash
###
### bootstrap.sh is run by the EC2 instance at startup.
### See $ROOT/template.yaml for details
###
### Idempotent: safe to run again after 'git pull'. Each numbered section
### has a guard file in /opt/webapp/var/. If the guard exists, the section
### is skipped so re-runs are fast.
###

set -euo pipefail
echo "=== Bootstrap: setting up Ubuntu 24.04 for PlantTracer ==="
export ROOT=/opt/webapp
cd "$ROOT"
mkdir -p /opt/webapp/var
VAR=/opt/webapp/var

guard_file() { printf '%s/.bootstrap_%02d' "$VAR" "$1"; }
run_section() {
  local n=$1
  local name="$2"
  local g
  g="$(guard_file "$n")"
  if [ -f "$g" ]; then
    echo "Section $n: $name (skipped, already done)"
    return 0
  fi
  echo "Section $n: $name"
  date | tee "$g"
  return 1
}
end_section() {
  local n=$1
  date | tee -a "$(guard_file "$n")"
}

## Load environment (always run; needed for vars below)
if [ -f /etc/environment.d/10-planttracer.conf ]; then
  source /etc/environment.d/10-planttracer.conf
fi
if [ -z "${AWS_REGION+x}" ]; then
  TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")
  AWS_REGION=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" -s http://169.254.169.254/latest/meta-data/placement/region)
  echo "AWS_REGION=$AWS_REGION" | sudo tee -a /etc/environment.d/10-planttracer.conf
fi
export AWS_REGION DOMAIN DYNAMODB_TABLE_PREFIX HOSTNAME LOG_LEVEL PLANTTRACER_S3_BUCKET
export ADMIN_EMAIL COURSE_ID ADMIN_NAME COURSE_NAME SERVER_EMAIL LAMBDA_RESIZE_ARN

# --- Section 1: Shell config (.bashrc, .bash_profile) ---
if ! run_section 1 "Shell config (.bashrc, .bash_profile)"; then
  if ! grep -q planttracer "$HOME/.bashrc" 2>/dev/null; then
    echo '# source planttracer
. "/etc/environment.d/10-planttracer.conf" && export $(cut -d= -f1 "/etc/environment.d/10-planttracer.conf" | grep -v "^#")
' >> "$HOME/.bashrc"
  fi
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
  end_section 1
fi

# --- Section 2: pipx and poetry ---
if ! run_section 2 "pipx and poetry"; then
  sudo apt-get update -y
  sudo apt-get install -y python3-pip pipx
  pipx ensurepath
  export PATH="$HOME/.local/bin:$PATH"
  sudo apt-get remove --purge -y poetry 2>/dev/null || true
  pipx install poetry --force 2>/dev/null || pipx upgrade poetry
  poetry --version
  poetry self add poetry-plugin-export
  end_section 2
fi
export PATH="$HOME/.local/bin:$PATH"

# --- Section 3: nginx and hostname ---
if ! run_section 3 "nginx and hostname"; then
  sudo hostnamectl set-hostname "$HOSTNAME.$DOMAIN"
  sudo apt-get install -y nginx
  end_section 3
fi

# --- Section 4: certbot (snap + symlink + reload hook) ---
if ! run_section 4 "certbot (snap + reload hook)"; then
  sudo snap install core
  sudo snap refresh core
  sudo snap install --classic certbot
  if [ ! -e /usr/bin/certbot ]; then
    sudo ln -sf /snap/bin/certbot /usr/bin/certbot
  fi
  sudo mkdir -p /etc/letsencrypt/renewal-hooks/deploy/
  sudo cp "$ROOT/etc/reload-server.sh" /etc/letsencrypt/renewal-hooks/deploy/
  end_section 4
fi

# --- Section 5: TLS certificate (certbot --nginx) ---
if ! run_section 5 "TLS certificate (certbot --nginx)"; then
  LETS_ENCRYPT_CONF=/etc/letsencrypt/renewal/$HOSTNAME.$DOMAIN.conf
  if [ -f "$LETS_ENCRYPT_CONF" ]; then
    echo "$LETS_ENCRYPT_CONF exists, skipping cert obtain."
  else
    sudo certbot --nginx --non-interactive --expand --cert-name "$HOSTNAME.$DOMAIN" \
      -d "$HOSTNAME.$DOMAIN" \
      -d "$HOSTNAME-demo.$DOMAIN" \
      --email plantadmin@planttracer.com --no-eff-email --agree-tos
  fi
  end_section 5
fi

# --- Section 6: nginx config (patch, test, reload, planttracer.service) ---
if ! run_section 6 "nginx config (patch, reload, systemd unit)"; then
  DEFAULT=/etc/nginx/sites-available/default
  if [ -r "$DEFAULT.certbot" ]; then
    sudo cp "$DEFAULT.certbot" "$DEFAULT"
  fi
  sudo cp -f "$DEFAULT" "$DEFAULT.certbot"
  echo "Adding $HOSTNAME.$DOMAIN to $DEFAULT"
  # Landmark: delete from after server_name up to and including first line that is only "}" (closing the location block)
  sudo python3 "$ROOT/etc/patcher.py" "$DEFAULT" "$ROOT/etc/planttracer-nginx-patch" 'server_name' \
    --flag planttracer-nginx-patch --delete-to '^\s*}\s*$' --save "$VAR"
  rm -f "$ROOT/etc/planttracer-nginx-patch.5100"
  sed 's/5000/5100/' "$ROOT/etc/planttracer-nginx-patch" > "$ROOT/etc/planttracer-nginx-patch.5100"
  echo "Adding $HOSTNAME-demo.$DOMAIN to $DEFAULT"
  sudo python3 "$ROOT/etc/patcher.py" "$DEFAULT" "$ROOT/etc/planttracer-nginx-patch.5100" "$HOSTNAME-demo.$DOMAIN" \
    --flag planttracer-nginx-patch.5100 --delete-to '^\s*}\s*$' --save "$VAR"
  nginx_test_out=$(sudo /usr/sbin/nginx -t 2>&1) || true
  nginx_exit=$?
  echo "$nginx_test_out" | grep -v 'the "user" directive' 1>&2 || true
  if [ "$nginx_exit" -ne 0 ]; then
    echo "CRITICAL: nginx config invalid after patch"
    [ -f "$DEFAULT.old" ] && sudo mv "$DEFAULT.old" "$DEFAULT"
    exit 1
  fi
  sudo systemctl reload nginx
  sudo cp "$ROOT/etc/planttracer.service" /etc/systemd/system/planttracer.service
  sudo systemctl daemon-reload
  end_section 6
fi

# --- Section 7: app install (venv, poetry install) ---
if ! run_section 7 "app install (make install-ubuntu, poetry install)"; then
  make install-ubuntu
  poetry install
  end_section 7
fi

# --- Section 8: demos (dbutil --create_demos) ---
if ! run_section 8 "demos (dbutil --create_demos)"; then
  poetry run python src/dbutil.py --create_demos
  end_section 8
fi

# --- Section 9: S3 (CORS presigned, Lambda trigger) ---
if ! run_section 9 "S3 (CORS, Lambda trigger)"; then
  if [ -n "${PLANTTRACER_S3_BUCKET:-}" ]; then
    poetry run python -m app.s3_presigned "$PLANTTRACER_S3_BUCKET" || true
  fi
  if [ -n "${PLANTTRACER_S3_BUCKET:-}" ] && [ -n "${LAMBDA_RESIZE_ARN:-}" ]; then
    poetry run python etc/s3_upload_trigger.py || true
  fi
  end_section 9
fi

# --- Section 10: create_course (idempotent) ---
if ! run_section 10 "create_course"; then
  if [ -n "${COURSE_ID:-}" ] && [ -n "${COURSE_NAME:-}" ] && [ -n "${ADMIN_EMAIL:-}" ] && [ -n "${ADMIN_NAME:-}" ]; then
    poetry run python src/dbutil.py --create_course \
      --course_id "$COURSE_ID" \
      --course_name "$COURSE_NAME" \
      --admin_email "$ADMIN_EMAIL" \
      --admin_name "$ADMIN_NAME" \
      --send-email
  fi
  end_section 10
fi

# --- Section 11: start planttracer service ---
if ! run_section 11 "start planttracer service"; then
  sudo systemctl daemon-reload
  sudo systemctl start planttracer.service
  sudo systemctl enable planttracer.service
  end_section 11
fi

echo "Bootstrap complete. Web server at https://$HOSTNAME.$DOMAIN and https://$HOSTNAME-demo.$DOMAIN"
