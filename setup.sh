#!/bin/bash
# Lab setup: runs at container start. Stages the pre-broken
# configs into place, applies the faults that cannot live in git
# (file ownership / firewall), then starts the services.
set -e

# 1. copy the (pre-broken) configs into the system paths
cp -f etc/bind/named.conf.options /etc/bind/named.conf.options
cp -f etc/bind/named.conf.local  /etc/bind/named.conf.local
cp -f etc/bind/db.novapeak.lab /etc/bind/db.novapeak.lab
cp -f etc/bind/db.novapeak.lab.rev /etc/bind/db.novapeak.lab.rev 2>/dev/null || true
cp -f etc/dhcp/dhcpd.conf /etc/dhcp/dhcpd.conf
cp -f etc/default/isc-dhcp-server /etc/default/isc-dhcp-server
chown bind:bind /etc/bind/db.novapeak.lab /etc/bind/db.novapeak.lab.rev 2>/dev/null || true

# 2. stage the student-safe grading tools
mkdir -p /root/grading
cp -f grading/*.py /root/grading/ 2>/dev/null || true
cp -f grading/.faults_applied /root/grading/ 2>/dev/null || true

# 3b. outside-git fault: drop inbound DNS at the firewall
iptables -I INPUT -p udp --dport 53 -j DROP

# 4. (re)start services; some faults intentionally prevent start
systemctl restart named 2>/dev/null || true
systemctl restart isc-dhcp-server 2>/dev/null || true

# 5. remove this setup script's traces of WHICH faults exist:
#    the setup.sh itself is the only clear record, so lock it down.
chmod 700 setup.sh 2>/dev/null || true
echo "Lab environment initialised."
