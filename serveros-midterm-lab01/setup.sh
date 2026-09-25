#!/bin/bash
# Background setup for Server OS Midterm Lab 01.
# KillerCoda runs this at container start but does NOT copy the scenario's
# asset files into the container -- so we DOWNLOAD them from the (public) repo
# raw URLs rather than relying on files being staged beside this script.
set -u

RAW="https://raw.githubusercontent.com/teaching-git/midterm-server-os/main/serveros-midterm-lab01/grading-assets"

echo "[setup] installing tools..."
apt-get update -qq 2>/dev/null || true
apt-get install -y bind9 bind9-utils dnsutils isc-dhcp-server dhcpcd-base \
    iproute2 iptables curl >/dev/null 2>&1 || true

mkdir -p /root/grading

# --- helper: download a file and verify it is non-empty ---
fetch() {
  # $1 = raw path under $RAW ; $2 = destination
  curl -fsSL "$RAW/$1" -o "$2" 2>/dev/null
  if [ ! -s "$2" ]; then
    echo "[setup][WARN] failed to fetch $1 -> $2"
    return 1
  fi
  return 0
}

echo "[setup] downloading grading scripts..."
fetch "grading/params.py"          /root/grading/params.py
fetch "grading/setup_lab_net.py"   /root/grading/setup_lab_net.py
fetch "grading/check_lab.py"       /root/grading/check_lab.py
fetch "grading/.faults_applied"    /root/grading/.faults_applied

echo "[setup] downloading (pre-broken) configs..."
fetch "etc/bind/named.conf.options" /etc/bind/named.conf.options
fetch "etc/bind/named.conf.local"   /etc/bind/named.conf.local
fetch "etc/bind/db.novapeak.lab"     /etc/bind/db.novapeak.lab
fetch "etc/bind/db.novapeak.lab.rev" /etc/bind/db.novapeak.lab.rev
fetch "etc/dhcp/dhcpd.conf"          /etc/dhcp/dhcpd.conf
fetch "etc/default/isc-dhcp-server"  /etc/default/isc-dhcp-server

# --- outside-git fault: iptables DROP on inbound DNS ---
iptables -I INPUT -p udp --dport 53 -j DROP 2>/dev/null || true

# --- fix ownership so bind can read its zone files (normal requirement) ---
chown bind:bind /etc/bind/db.novapeak.lab /etc/bind/db.novapeak.lab.rev 2>/dev/null || true

systemctl restart named 2>/dev/null || true
systemctl restart isc-dhcp-server 2>/dev/null || true

# --- verification: did the essential scripts arrive? ---
MISSING=""
for f in params.py setup_lab_net.py check_lab.py; do
  [ -s "/root/grading/$f" ] || MISSING="$MISSING $f"
done
if [ -n "$MISSING" ]; then
  echo "[setup][ERROR] these scripts did NOT download:$MISSING" > /root/.lab_ready
  echo "[setup] Check the repo is PUBLIC and the raw paths are correct." >> /root/.lab_ready
else
  echo "Lab 01 ready (grading scripts downloaded OK)" > /root/.lab_ready
fi
