#!/usr/bin/env bash
set -euo pipefail
echo Setting up ubuntu 22.04 running in AWS for PlantTracer.
"""
to-do:
Reliability (EC2 bootstrap)
Make the app a systemd service instead of exec "${GitRunPath}" in user-data
User-data is one-shot; you’ll want restart-on-failure and start-on-boot semantics
In user-data, write a unit file and systemctl enable --now yourservice. Keep the git checkout/update logic, but run it from a controlled service/script.
"""



echo Hello World.
