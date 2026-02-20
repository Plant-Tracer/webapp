#!/bin/bash
# Certbot provides the $RENEWED_DOMAINS variable if you need to check the domain
echo "Renewed domains: $RENEWED_DOMAINS" >> /var/log/certbot-hooks.log
systemctl reload nginx
