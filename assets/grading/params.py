#!/usr/bin/env python3
"""Per-group scenario parameters for the Server OS midterm.

Every group runs a different fictional company, derived deterministically from
the group id. Because the DNS records, network, pool and the all-important
"which resolver does DHCP advertise" value all differ per group, one group's
finished configuration is useless to another -- copying fails by construction.

WHY hashlib and not hash(): Python's built-in hash() is salted randomly per
process (PYTHONHASHSEED), so it would give different results on every run and
between machines. We need the SAME group id to map to the SAME company every
time, on any box, so we use a stable SHA-256 of the id. An instructor salt
(SERVEROS_SALT) lets you reshuffle the assignment between terms without editing
code.

This module is imported by the grader, the fault injector, the answer key, the
flawed-config generator and the quiz bank, so it is the single source of truth
for "what was this group asked to build".
"""

import hashlib
import os

# Fictional companies. Kept deliberately boring and unambiguous so students
# type them correctly (no punctuation, no easily-confused characters).
_COMPANIES = [
    "cedarworks", "novapeak", "harborlight", "quartzbay",
    "emberfield", "willowgate", "cobaltmill", "aspenridge",
    "onyxharbor", "deltaforge", "lumenworks", "basaltco",
    "crimsonpeak", "meadowlane", "vertexlab", "falconry",
]

# App-host names: the fourth service each company runs, varied per group.
_APP_NAMES = ["portal", "shop", "intranet", "api", "wiki", "dashboard"]


def _seed(group_id):
    """Return a large stable integer derived from the group id and the optional
    instructor salt. Deterministic across runs and machines (unlike hash())."""
    salt = os.environ.get("SERVEROS_SALT", "")
    material = (salt + "|" + group_id.strip().lower()).encode("utf-8")
    return int(hashlib.sha256(material).hexdigest(), 16)


def group_params(group_id):
    """Compute the full scenario for one group.

    All addresses live in 192.168.<octet>.0/24 where <octet> is derived from
    the id, so each group has its own subnet and there is no collision between
    the service network and the playground's own eth0 (which we never touch)."""
    gid = group_id.strip().lower()
    h = _seed(gid)

    company = _COMPANIES[h % len(_COMPANIES)]
    domain = company + ".lab"

    # Third octet 10..209 -> 192.168.<octet>.0/24. Avoids .0/.1 low range and
    # stays clear of common host networks to reduce surprise clashes.
    octet = 10 + (h % 200)
    net = "192.168.%d" % octet

    # Fixed roles within the subnet. Chosen as constants (not hashed) so the
    # scenario is easy for a student to hold in their head: .1 gateway,
    # .10 DNS, .20 www, .30 mail, .40 app. The POOL is what varies most.
    dns_ip = "%s.10" % net
    gateway = "%s.1" % net
    www_ip = "%s.20" % net
    mail_ip = "%s.30" % net
    app_ip = "%s.40" % net

    # DHCP pool: start varies 100..119, span fixed at 40 addresses.
    pool_start_host = 100 + (h // 7 % 20)
    pool_end_host = pool_start_host + 40
    pool_start = "%s.%d" % (net, pool_start_host)
    pool_end = "%s.%d" % (net, pool_end_host)

    # A reserved host (the "printer") used in the Part 5 change request. Its MAC
    # is derived from the id so the spoofing task is unique per group.
    mac_tail = format((h >> 12) & 0xFFFFFF, "06x")
    printer_mac = "de:ad:%s:%s:%s:%s" % (
        mac_tail[0:2], mac_tail[2:4], mac_tail[4:6], format(h % 256, "02x"))
    printer_ip = "%s.%d" % (net, 200 + (h // 11 % 30))  # .200..229, outside pool

    app_name = _APP_NAMES[h % len(_APP_NAMES)]
    lease = [3600, 7200, 21600][h % 3]

    # Second subnet for Part 5 (the "new branch office"). Different octet.
    octet2 = 10 + ((h // 13) % 200)
    if octet2 == octet:  # guarantee distinct from the primary subnet
        octet2 = octet + 1 if octet < 209 else octet - 1
    net2 = "192.168.%d" % octet2

    # Reverse zone name for the primary subnet (in-addr.arpa for the /24).
    rev_zone = "%d.168.192.in-addr.arpa" % octet

    return {
        "group_id": gid,
        "company": company,
        "domain": domain,
        "network": "%s.0" % net,
        "netmask": "255.255.255.0",
        "cidr": "%s.0/24" % net,
        "gateway": gateway,
        "dns_ip": dns_ip,          # the resolver DHCP MUST advertise
        "www_ip": www_ip,
        "mail_ip": mail_ip,
        "app_name": app_name,
        "app_ip": app_ip,
        "pool_start": pool_start,
        "pool_end": pool_end,
        "lease": lease,
        "printer_mac": printer_mac,
        "printer_ip": printer_ip,
        "rev_zone": rev_zone,
        # Part 5 second subnet:
        "network2": "%s.0" % net2,
        "gateway2": "%s.1" % net2,
        "dns_ip2": "%s.10" % net2,
        "pool2_start": "%s.100" % net2,
        "pool2_end": "%s.140" % net2,
        "mx_priority": 10,
    }


def _fmt(p):
    """Human-readable scenario card printed to the student."""
    L = []
    L.append("=" * 64)
    L.append("  Server OS Midterm -- scenario for group '%s'" % p["group_id"])
    L.append("=" * 64)
    L.append("  Company / domain     : %s  ->  %s" % (p["company"], p["domain"]))
    L.append("  Service network      : %s   gateway %s" % (p["cidr"], p["gateway"]))
    L.append("  DNS server (ns1) IP  : %s   <-- DHCP MUST advertise this" % p["dns_ip"])
    L.append("  DHCP pool            : %s .. %s" % (p["pool_start"], p["pool_end"]))
    L.append("  Lease time           : %d seconds" % p["lease"])
    L.append("")
    L.append("  DNS zone must contain these A records:")
    L.append("    ns1.%-22s -> %s" % (p["domain"], p["dns_ip"]))
    L.append("    www.%-22s -> %s" % (p["domain"], p["www_ip"]))
    L.append("    mail.%-21s -> %s" % (p["domain"], p["mail_ip"]))
    L.append("    %s.%-*s -> %s" % (p["app_name"], 22 - len(p["app_name"]),
                                    p["domain"], p["app_ip"]))
    L.append("")
    L.append("  Reverse zone         : %s" % p["rev_zone"])
    L.append("  Service network is on interface: lan0  (NOT eth0)")
    L.append("=" * 64)
    return "\n".join(L)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python3 params.py GROUP_ID")
        sys.exit(1)
    print(_fmt(group_params(sys.argv[1])))
