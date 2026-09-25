#!/bin/bash
# Applies ONLY the outside-git faults for lab01 (the ones that cannot be baked
# into committed files): here, the iptables DROP on inbound DNS.
# The file-content faults are already baked into the staged configs.
# (lab01's draw: A_bad_zone_path, C_wrong_resolver, D_app_points_at_gateway are
#  baked; B_iptables_drop is applied here.)
iptables -I INPUT -p udp --dport 53 -j DROP 2>/dev/null || true
