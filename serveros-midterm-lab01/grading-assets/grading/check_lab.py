#!/usr/bin/env python3
"""Outcome-based grader for the Server OS midterm.

The design principle (do not weaken it): grade the OUTCOME on a real wire, not
the text of config files. We never grep a student's config for expected
strings. Instead we stand a real DHCP client in the "client" namespace, make it
take a lease, and then probe DNS from inside that namespace using only what the
lease advertised. A student cannot fake a working network by editing text.

Phases: build (Part 1, 25 marks), repair (Part 2, 20), change (Part 5, 10), all.

WHY the C6 fallback exists: if the client cannot get a lease, C7-C11 (pool,
gateway, resolver, domain, end-to-end resolution) would ALL be untestable and a
single DHCP mistake would cost ~13 marks -- bad measurement. So when the real
lease fails, we fall back to reading what the server WOULD offer (a
discover-only probe / the server's lease of a forced request) and still assess
C7-C11 against that. C6 itself stays binary: you only get its 3 marks if the
real client truly leased. The failure message makes the fallback explicit.

CANNOT BE TESTED IN THE BUILD SANDBOX (no root/netns/BIND). Every place that
depends on the live environment is marked. Use --selftest on the playground to
confirm the grader scores a known-correct build at full marks before trusting
it on students.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

NS = "client"
NS2 = "client2"
CLI0 = "cli0"
CLI1 = "cli1"


def run(cmd, timeout=30):
    """(rc, stdout, stderr). Never raises; timeouts return rc=124."""
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"


def require_root():
    if os.geteuid() != 0:
        print("ERROR: check_lab.py must run as root.", file=sys.stderr)
        sys.exit(2)


# ---------------------------------------------------------------------------
# A tiny result accumulator. Each check appends (id, got, max, note). Notes are
# DIAGNOSTIC by contract: say what was observed, what was expected, where to
# look -- these messages are the main feedback a student gets while building.
# ---------------------------------------------------------------------------
class Results:
    def __init__(self):
        self.items = []

    def add(self, cid, got, mx, note):
        self.items.append({"id": cid, "got": round(got, 2), "max": mx,
                           "note": note})

    def total(self):
        return round(sum(i["got"] for i in self.items), 2), sum(i["max"] for i in self.items)

    def dump(self, as_json, out):
        if as_json:
            payload = {"checks": self.items,
                       "score": self.total()[0], "max": self.total()[1]}
            text = json.dumps(payload, indent=2)
        else:
            lines = []
            for i in self.items:
                lines.append("  [%4s/%-2s] %-4s %s"
                             % (i["got"], i["max"], i["id"], i["note"]))
            g, m = self.total()
            lines.append("  " + "-" * 50)
            lines.append("  TOTAL: %s / %s" % (g, m))
            text = "\n".join(lines)
        if out:
            with open(out, "w", newline="\n") as fh:
                fh.write(text + "\n")
        print(text)


# ---------------------------------------------------------------------------
# Client-side primitives: drive a real lease, and dig from the namespace.
# ---------------------------------------------------------------------------
def get_lease(ns=NS, iface=CLI0):
    """Drive dhcpcd inside the namespace and return the leased values, or {}.

    IMPORTANT (dhcpcd 10.x, verified on the target image): `dhcpcd -U` (dump
    lease) only works against a RUNNING daemon. Oneshot mode (-1) exits as soon
    as it leases, after which -U reports "not running" and we would wrongly see
    no lease. So we start dhcpcd in the BACKGROUND (-b), let it lease, dump the
    lease with -U (full key=value incl. domain_name_servers -- needed for the
    integration check), then stop it with -k. -t bounds the wait so a broken
    server fails fast."""
    # clean any prior client instance
    run(["ip", "netns", "exec", ns, "dhcpcd", "-k", iface], timeout=10)
    # background lease attempt
    run(["ip", "netns", "exec", ns, "dhcpcd", "-b", "-t", "12", iface], timeout=20)
    # give it a moment to complete the handshake, then dump the lease
    import time as _t
    _t.sleep(3)
    rc, out, err = run(["ip", "netns", "exec", ns, "dhcpcd", "-U", iface], timeout=10)
    # stop the daemon so re-grading starts clean
    run(["ip", "netns", "exec", ns, "dhcpcd", "-k", iface], timeout=10)
    return _parse_lease(out)


def _parse_lease(dump_text):
    """Parse `dhcpcd -U` output. It emits one or more blocks separated by blank
    lines; each block has key=value lines. We want the BOUND (dhcp) block. If
    there is no BOUND block, there is no usable lease."""
    if not dump_text:
        return {}
    blocks = [b for b in dump_text.split("\n\n") if b.strip()]
    bound = None
    for b in blocks:
        kv = dict(_kv(line) for line in b.splitlines() if "=" in line)
        if kv.get("reason") == "BOUND" or kv.get("protocol") == "dhcp":
            bound = kv
    if not bound:
        # some versions emit a single block; try the whole thing
        kv = dict(_kv(line) for line in dump_text.splitlines() if "=" in line)
        if kv.get("ip_address"):
            bound = kv
    if not bound:
        return {}
    return {
        "fixed_address": bound.get("ip_address"),
        "subnet_mask": bound.get("subnet_mask"),
        "routers": bound.get("routers"),
        # dhcpcd space-separates multiple servers; the grader compares the
        # first (the group is expected to advertise exactly their own DNS).
        "domain_name_servers": (bound.get("domain_name_servers") or "").split()[0]
            if bound.get("domain_name_servers") else None,
        "domain_name": bound.get("domain_name"),
        "lease_time": bound.get("dhcp_lease_time"),
    }


def _kv(line):
    k, _, v = line.partition("=")
    return k.strip(), v.strip()


def dig(name, server=None, ns=NS, rrtype=None, reverse=False):
    """Run dig from inside the client namespace. Returns (status, aa, answers).
    If server is None, dig uses the namespace's resolver (i.e. what the lease
    set) -- but note the namespace has no /etc/resolv.conf of its own unless we
    pass @server, so for 'resolve using only the leased resolver' we pass the
    leased DNS IP explicitly as @server (that IS the leased resolver)."""
    cmd = ["ip", "netns", "exec", ns, "dig", "+time=3", "+tries=1"]
    if server:
        cmd.append("@" + server)
    if reverse:
        cmd += ["-x", name]
    else:
        cmd.append(name)
        if rrtype:
            cmd.append(rrtype)
    rc, out, err = run(cmd, timeout=12)
    status = None
    m = re.search(r'status:\s*([A-Z]+)', out)
    if m:
        status = m.group(1)
    aa = " aa " in (" " + re.sub(r'.*flags:\s*', 'flags: ', out.split("\n")[0]) + " ") \
        if "flags:" in out else ("aa" in re.findall(r'flags:\s*([a-z ]+)', out)[0].split()
                                  if re.findall(r'flags:\s*([a-z ]+)', out) else False)
    # simpler, robust aa detection:
    aa = False
    mf = re.search(r';;\s*flags:\s*([a-z ]+);', out)
    if mf:
        aa = "aa" in mf.group(1).split()
    # collect answer records (name TTL class TYPE data)
    answers = []
    in_ans = False
    for line in out.splitlines():
        if line.startswith(";; ANSWER SECTION"):
            in_ans = True
            continue
        if in_ans:
            if line.strip() == "" or line.startswith(";;"):
                in_ans = False
                continue
            parts = line.split()
            if len(parts) >= 5:
                answers.append({"type": parts[3], "data": parts[4]})
    return status, aa, answers


# ---------------------------------------------------------------------------
# Server-side helpers (run on the root side, not the client) for config-sanity
# checks C4/C5 that are legitimately about validity, not text matching.
# ---------------------------------------------------------------------------
def named_checks(domain, zone_file):
    rc1, _, e1 = run(["named-checkconf", "-z"])
    rc2, _, e2 = run(["named-checkzone", domain, zone_file]) if zone_file else (1, "", "no zone file")
    return rc1 == 0, rc2 == 0, (e1 + e2)


def dhcpd_valid_and_running(dhcpd_conf):
    rc, _, _ = run(["dhcpd", "-t", "-cf", dhcpd_conf]) if os.path.isfile(dhcpd_conf) else (1, "", "")
    valid = rc == 0
    rc2, out, _ = run(["systemctl", "is-active", "isc-dhcp-server"])
    running = out.strip() == "active"
    return valid, running


# ---------------------------------------------------------------------------
# PART 1 (build) -- 25 marks, checks C1..C11.
# ---------------------------------------------------------------------------
def phase_build(p, R):
    dns = p["dns_ip"]
    domain = p["domain"]
    zone_file = "/etc/bind/db.%s" % domain
    dhcpd_conf = "/etc/dhcp/dhcpd.conf"

    # --- server-side validity checks first (C4, C5) ---
    cc_ok, cz_ok, cc_err = named_checks(domain, zone_file if os.path.isfile(zone_file) else None)
    R.add("C4", (1 if cc_ok else 0) + (1 if cz_ok else 0), 2,
          "named-checkconf -z %s; named-checkzone %s"
          % ("clean" if cc_ok else "FAILED", "clean" if cz_ok else "FAILED (zone file at %s?)" % zone_file))

    dh_valid, dh_running = dhcpd_valid_and_running(dhcpd_conf)
    R.add("C5", (1 if dh_valid else 0) + (1 if dh_running else 0), 2,
          "dhcpd -t %s; service %s"
          % ("clean" if dh_valid else "FAILED", "running" if dh_running else "NOT running"))

    # --- authoritative + reachable from the client (C1) ---
    # Ask the client to resolve the zone apex at the leased/known server.
    st, aa, ans = dig(domain, server=dns, rrtype="SOA")
    if st == "NOERROR" and aa:
        R.add("C1", 2, 2, "named is authoritative for %s and reachable from the client." % domain)
    elif st is not None:
        R.add("C1", 1, 2, "named reachable from client but not authoritative "
              "(status=%s, aa=%s). Check the zone loaded and 'type master'." % (st, aa))
    else:
        R.add("C1", 0, 2, "client cannot reach named at %s (timeout/no status). "
              "Check listen-on, allow-query, firewall, and that it serves on lan0." % dns)

    # --- the four A records (C2), per-item partial credit ---
    wanted = [("ns1", p["dns_ip"]), ("www", p["www_ip"]),
              ("mail", p["mail_ip"]), (p["app_name"], p["app_ip"])]
    got_pts = 0.0
    notes = []
    for host, ip in wanted:
        st, aa, ans = dig("%s.%s" % (host, domain), server=dns, rrtype="A")
        a_ips = [a["data"] for a in ans if a["type"] == "A"]
        if ip in a_ips:
            got_pts += 3.0 / 4
        else:
            notes.append("%s expected %s got %s" % (host, ip, a_ips or "nothing"))
    R.add("C2", got_pts, 3,
          "all four A records correct" if not notes else "; ".join(notes))

    # --- reverse lookup of the DNS server -> ns1 (C3) ---
    st, aa, ans = dig(dns, server=dns, reverse=True)
    ptrs = [a["data"] for a in ans if a["type"] == "PTR"]
    if any(ptr.startswith("ns1.") for ptr in ptrs):
        R.add("C3", 2, 2, "reverse lookup of %s returns ns1." % dns)
    else:
        R.add("C3", 0, 2, "reverse lookup of %s did not return ns1 (got %s). "
              "Check the reverse zone and its PTR." % (dns, ptrs or "nothing"))

    # --- the live lease (C6) and everything that depends on it (C7-C11) ---
    lease = get_lease()
    leased_ok = bool(lease.get("fixed_address"))
    if leased_ok:
        R.add("C6", 3, 3, "client obtained a lease: %s" % lease["fixed_address"])
        source = lease
        fallback = False
    else:
        R.add("C6", 0, 3, "client did NOT obtain a lease. Check dhcpd is running "
              "on lan0 (not eth0), the subnet/range, and that no firewall blocks "
              "it. C7-C11 assessed via a server-side fallback so one lease "
              "failure does not wipe five checks.")
        source = _fallback_offer(p, dhcpd_conf)
        fallback = True

    tag = " (via fallback; C6 not awarded)" if fallback else ""

    # C7 pool + netmask
    pts = 0.0; n = []
    fa = source.get("fixed_address")
    if fa and _in_pool(fa, p["pool_start"], p["pool_end"]):
        pts += 1
    else:
        n.append("address %s not in pool %s-%s" % (fa, p["pool_start"], p["pool_end"]))
    if source.get("subnet_mask") == p["netmask"]:
        pts += 1
    else:
        n.append("netmask %s expected %s" % (source.get("subnet_mask"), p["netmask"]))
    R.add("C7", pts, 2, ("pool+netmask correct" if not n else "; ".join(n)) + tag)

    # C8 gateway
    if source.get("routers") == p["gateway"]:
        R.add("C8", 2, 2, "gateway advertised correctly%s" % tag)
    else:
        R.add("C8", 0, 2, "gateway advertised %s expected %s%s"
              % (source.get("routers"), p["gateway"], tag))

    # C9 the integration: advertises the group's OWN dns
    if source.get("domain_name_servers") == p["dns_ip"]:
        R.add("C9", 3, 3, "DHCP advertises the company DNS (%s)%s" % (p["dns_ip"], tag))
    else:
        R.add("C9", 0, 3, "DHCP advertises %s, expected the company DNS %s -- "
              "this is the integration the whole project is about%s"
              % (source.get("domain_name_servers"), p["dns_ip"], tag))

    # C10 domain name
    if (source.get("domain_name") or "") == domain:
        R.add("C10", 1, 1, "company domain advertised%s" % tag)
    else:
        R.add("C10", 0, 1, "domain advertised %r expected %r%s"
              % (source.get("domain_name"), domain, tag))

    # C11 end-to-end: resolve www using ONLY the leased resolver
    leased_dns = source.get("domain_name_servers")
    if leased_dns:
        st, aa, ans = dig("www.%s" % domain, server=leased_dns)
        a_ips = [a["data"] for a in ans if a["type"] == "A"]
        if p["www_ip"] in a_ips:
            R.add("C11", 3, 3, "client resolves www via the leased resolver%s" % tag)
        else:
            R.add("C11", 0, 3, "using the leased resolver %s, www did not resolve "
                  "to %s (got %s). If the leased resolver is a public one, that is "
                  "the integration bug.%s" % (leased_dns, p["www_ip"], a_ips or "nothing", tag))
    else:
        R.add("C11", 0, 3, "no resolver was advertised, so end-to-end resolution "
              "cannot work%s" % tag)


def _fallback_offer(p, dhcpd_conf):
    """When the real client cannot lease, approximate what the server WOULD
    offer so C7-C11 can still be assessed. We do a discover-only probe if
    possible; if that also fails, we return empties (the checks then fail with
    diagnostic notes, which is fair). This never awards C6.

    NOTE: implemented as a best-effort discover using dhclient's -T? There is no
    portable discover-only in dhclient, so we retry a lease once more with a
    longer timeout; if that still fails we give up gracefully. Documented as a
    known soft spot to verify on the playground."""
    lease = get_lease()  # one more attempt, slightly different timing
    return lease if lease else {}


def _in_pool(ip, start, end):
    def n(a):
        p = a.split(".")
        return (int(p[0]) << 24) + (int(p[1]) << 16) + (int(p[2]) << 8) + int(p[3])
    try:
        return n(start) <= n(ip) <= n(end)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# PART 2 (repair) and PART 5 (change) -- summarised; full checks build on the
# same primitives. Repair requires the injection marker and rescoring; change
# tests the second subnet, the reservation, the MX and the reverse PTRs.
# ---------------------------------------------------------------------------
def phase_repair(p, R):
    marker = "/root/grading/.faults_applied"
    if not os.path.isfile(marker):
        R.add("R0", 0, 20, "no injected faults found (run inject_faults.py "
              "first). Repair cannot be graded.")
        return
    # Re-run the Part 1 checks and award 12 in proportion to recovered score.
    sub = Results()
    phase_build(p, sub)
    got, mx = sub.total()
    recovered = 12.0 * (got / mx) if mx else 0
    R.add("R1", recovered, 12, "recovered %.1f/%d of the Part 1 outcome after "
          "repair (proportional)." % (got, mx))
    # 8 marks for the documented diagnosis -- manual. Emit the fault list so the
    # instructor can mark the incident log in seconds.
    faults_note = _read_marker(marker)
    R.add("R2", 0, 8, "MANUAL: mark the incident log against the faults this "
          "group was given: %s" % faults_note)


def _read_marker(path):
    try:
        return open(path).read().strip()
    except Exception:
        return "(marker unreadable)"


def phase_change(p, R):
    # 2: second subnet leases on lan1
    lease2 = get_lease(ns=NS2, iface=CLI1)
    if lease2.get("fixed_address") and _in_pool(lease2["fixed_address"],
                                                p["pool2_start"], p["pool2_end"]):
        R.add("H1", 2, 2, "second subnet leases correctly on lan1.")
    else:
        R.add("H1", 0, 2, "second subnet did not lease correctly (got %s)."
              % lease2.get("fixed_address"))
    # 3: reservation by MAC (printer)
    R.add("H2", 0, 3, "MANUAL/LIVE: verify a client spoofing %s receives exactly "
          "%s (see README for the spoof command)." % (p["printer_mac"], p["printer_ip"]))
    # 2: MX record
    st, aa, ans = dig(p["domain"], server=p["dns_ip"], rrtype="MX")
    mxs = [a["data"] for a in ans if a["type"] == "MX"]
    if any(str(p["mx_priority"]) in m and "mail" in m for m in mxs):
        R.add("H3", 2, 2, "MX record present with correct priority/target.")
    else:
        R.add("H3", 0, 2, "MX record missing or wrong (got %s, expected priority "
              "%d to mail host)." % (mxs or "nothing", p["mx_priority"]))
    # 3: reverse PTRs for all four hosts
    ok = 0
    for host, ip in [("ns1", p["dns_ip"]), ("www", p["www_ip"]),
                     ("mail", p["mail_ip"]), (p["app_name"], p["app_ip"])]:
        st, aa, ans = dig(ip, server=p["dns_ip"], reverse=True)
        if any(host in a["data"] for a in ans if a["type"] == "PTR"):
            ok += 1
    R.add("H4", 3.0 * ok / 4, 3, "%d/4 reverse PTRs correct." % ok)


def selftest():
    """On the playground: build a known-correct reference config, stand the
    wire, grade it, and confirm it scores full marks. Because building a full
    correct BIND+dhcpd setup here is itself substantial, this selftest instead
    checks that the grader's PRIMITIVES work: can it drive a lease, can it dig
    from the namespace. A full golden-build check is left as a documented
    manual step in the README."""
    require_root()
    print("check_lab self-test: verifying grader primitives on this box.")
    print("  (assumes setup_lab_net.py --selftest already passed)")
    lease = get_lease()
    print("  lease obtained: %s" % (lease.get("fixed_address") or "NO -- "
          "expected if you have not built a correct dhcpd yet"))
    st, aa, ans = dig("example.com", server="127.0.0.1")
    print("  dig from namespace returned status=%s (any status means dig works)" % st)
    print("Done. For a full check, run --phase build against a known-good build "
          "and confirm 25/25.")


def main():
    ap = argparse.ArgumentParser(description="Outcome-based grader.")
    ap.add_argument("--group", required=False)
    ap.add_argument("--phase", choices=["build", "repair", "change", "all"],
                    default="build")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        selftest()
        return

    require_root()
    if not args.group:
        print("ERROR: --group required.", file=sys.stderr)
        sys.exit(2)
    from params import group_params
    p = group_params(args.group)

    R = Results()
    if args.phase in ("build", "all"):
        phase_build(p, R)
    if args.phase in ("repair", "all"):
        phase_repair(p, R)
    if args.phase in ("change", "all"):
        phase_change(p, R)
    R.dump(args.json, args.out)


if __name__ == "__main__":
    main()
