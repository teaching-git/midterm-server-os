#!/bin/bash
# Runs automatically when the scenario container starts.
# Stage the lab content and initialise the (broken) environment.
set -e
mkdir -p /root/lab
# KillerCoda makes the repo available; copy the assets into place.
if [ -d "$(dirname "$0")/assets" ]; then
  cp -r "$(dirname "$0")/assets/." /root/lab/
fi
cd /root/lab
# ensure the DHCP client + tools are present for the grader
apt-get update -qq 2>/dev/null || true
apt-get install -y dhcpcd-base dnsutils iproute2 iptables bind9 bind9-utils isc-dhcp-server >/dev/null 2>&1 || true
# run the lab's own setup (stages broken configs, applies outside-git faults)
bash /root/lab/setup.sh 2>/dev/null || true
echo "Lab 01 environment ready in /root/lab" > /root/.lab_ready
