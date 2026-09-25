#!/bin/bash
# Background setup for Server OS Midterm Lab 01.
# KillerCoda does NOT stage the scenario's asset files into the container, so we
# DOWNLOAD the grading scripts and (pre-broken) configs from the public repo's
# raw URLs. We then build the lab wire BEFORE starting the services, because
# dhcpd refuses to start unless the interface it serves (lan0) already exists.
set -u

RAW="https://raw.githubusercontent.com/teaching-git/midterm-server-os/main/serveros-midterm-lab01/grading-assets"

echo "[setup] installing tools..."
apt-get update -qq 2>/dev/null || true
apt-get install -y bind9 bind9-utils dnsutils isc-dhcp-server dhcpcd-base \
    iproute2 iptables curl >/dev/null 2>&1 || true

mkdir -p /root/grading

fetch() {  # $1 raw-path ; $2 dest
  curl -fsSL "$RAW/$1" -o "$2" 2>/dev/null
  [ -s "$2" ] || { echo "[setup][WARN] failed to fetch $1"; return 1; }
  return 0
}

echo "[setup] downloading grading scripts..."
fetch "grading/params.py"        /root/grading/params.py
fetch "grading/setup_lab_net.py" /root/grading/setup_lab_net.py
fetch "grading/check_lab.py"     /root/grading/check_lab.py
fetch "grading/.faults_applied"  /root/grading/.faults_applied

echo "[setup] downloading (pre-broken) configs..."
fetch "etc/bind/named.conf.options"  /etc/bind/named.conf.options
fetch "etc/bind/named.conf.local"    /etc/bind/named.conf.local
fetch "etc/bind/db.novapeak.lab"     /etc/bind/db.novapeak.lab
fetch "etc/bind/db.novapeak.lab.rev" /etc/bind/db.novapeak.lab.rev
fetch "etc/dhcp/dhcpd.conf"          /etc/dhcp/dhcpd.conf
fetch "etc/default/isc-dhcp-server"  /etc/default/isc-dhcp-server

# --- BUILD THE WIRE FIRST: dhcpd needs lan0 to exist before it can start ---
echo "[setup] building the lab wire (lan0 <-> client namespace)..."
python3 /root/grading/setup_lab_net.py --group lab01 2>/dev/null || true

# --- outside-git fault: iptables DROP on inbound DNS ---
iptables -I INPUT -p udp --dport 53 -j DROP 2>/dev/null || true

# --- ownership so bind can read its zone files ---
chown bind:bind /etc/bind/db.novapeak.lab /etc/bind/db.novapeak.lab.rev 2>/dev/null || true

# --- NOW start the services (wire exists, so dhcpd can bind lan0) ---
echo "[setup] starting services..."
systemctl restart named 2>/dev/null || true
systemctl restart isc-dhcp-server 2>/dev/null || true

# --- verification ---
MISSING=""
for f in params.py setup_lab_net.py check_lab.py; do
  [ -s "/root/grading/$f" ] || MISSING="$MISSING $f"
done
if [ -n "$MISSING" ]; then
  echo "[setup][ERROR] scripts did not download:$MISSING" > /root/.lab_ready
else
  echo "Lab 01 ready (wire built, services started)" > /root/.lab_ready
fi
