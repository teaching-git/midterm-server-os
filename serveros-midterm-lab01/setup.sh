#!/bin/bash
# Background setup for the scenario. KillerCoda runs this at container start.
# It installs the tools, stages the (broken) lab from grading-assets, applies
# the outside-git faults, and starts the services.
set -e
D="$(dirname "$0")/grading-assets"

apt-get update -qq 2>/dev/null || true
apt-get install -y bind9 bind9-utils dnsutils isc-dhcp-server dhcpcd-base iproute2 iptables >/dev/null 2>&1 || true

# stage the pre-broken configs into the system
cp -f "$D"/etc/bind/named.conf.options /etc/bind/named.conf.options 2>/dev/null || true
cp -f "$D"/etc/bind/named.conf.local  /etc/bind/named.conf.local 2>/dev/null || true
cp -f "$D"/etc/bind/db.* /etc/bind/ 2>/dev/null || true
cp -f "$D"/etc/dhcp/dhcpd.conf /etc/dhcp/dhcpd.conf 2>/dev/null || true
cp -f "$D"/etc/default/isc-dhcp-server /etc/default/isc-dhcp-server 2>/dev/null || true

# stage the student-safe grading scripts
mkdir -p /root/grading
cp -f "$D"/grading/*.py /root/grading/ 2>/dev/null || true
cp -f "$D"/grading/.faults_applied /root/grading/ 2>/dev/null || true

# apply the outside-git faults (ownership / firewall) via the applier script
bash "$D"/apply_faults.sh 2>/dev/null || true

systemctl restart named 2>/dev/null || true
systemctl restart isc-dhcp-server 2>/dev/null || true
echo "Lab 01 ready" > /root/.lab_ready
