#!/bin/bash
set -a
source /etc/environment.d/10-planttracer.conf
set +a
cd /opt/webapp
poetry run python -c 'import src.app.odb as odb; print(odb.DDBO());'
