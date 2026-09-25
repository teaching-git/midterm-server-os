#!/usr/bin/env python3
"""Build the lab "wire": a client on the far end of a real network segment.

WHY THIS EXISTS
The playground's eth0 is the container's uplink and cannot be used as a service
network to grade against. So we synthesise a real segment with a veth pair:

    root namespace                          netns "client"
    +-----------------+                     +------------------+
    | lan0            |=== veth pair ======>| cli0 (NO address)|
    | <group DNS IP>  |                     | must DHCP for one|
    +-----------------+                     +------------------+

The student runs BIND and dhcpd bound to lan0. The grader then stands a real
DHCP client inside the "client" namespace on cli0, which has no address, so it
MUST obtain everything (address, gateway, resolver, domain) by DHCP -- exactly
the outcome we want to grade. Nothing about this can be faked by editing a
config file, which is the whole point.

HARD ENVIRONMENT RISKS (read before deploying):
  * `ip netns` requires kernel support and privileges some container hosts
    withhold. --selftest checks this FIRST and fails loudly if namespaces are
    not available, because nothing else can work without them.
  * systemd-resolved may hold 127.0.0.53:53 and interfere with the student's
    BIND. We detect and stand it down (DNSStubListener=no), printing what we
    did and why -- this is environment plumbing, not a learning objective. It
    may not be present at all in your image; that is fine.

I cannot test this file in the build sandbox (no root, no netns). Run
`python3 setup_lab_net.py --selftest` on the real playground first; it verifies
each step and reports exactly what works.
"""

import argparse
import os
import subprocess
import sys

# Names are fixed so the grader and the handout can refer to them.
NS = "client"
NS2 = "client2"
LAN0 = "lan0"          # root-side interface, holds the DNS server address
CLI0 = "cli0"          # client-side interface, no address (must DHCP)
LAN1 = "lan1"          # Part 5 second-subnet root side
CLI1 = "cli1"          # Part 5 client side


def run(cmd, check=False, quiet=False):
    """Run a command, returning (rc, stdout, stderr). Never raises unless
    check=True. We mostly do not check, because several steps are idempotent
    'ensure' operations that harmlessly fail if already done."""
    if not quiet:
        print("    $ " + " ".join(cmd))
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       text=True)
    if check and p.returncode != 0:
        raise RuntimeError("command failed: %s\n%s" % (" ".join(cmd), p.stderr))
    return p.returncode, p.stdout, p.stderr


def require_root():
    if os.geteuid() != 0:
        print("ERROR: must run as root (the playground gives you root).",
              file=sys.stderr)
        sys.exit(2)


# ---------------------------------------------------------------------------
# systemd-resolved: get it off :53 so the student's BIND can bind there and so
# the client's resolver behaviour is not muddied by a stub listener.
# ---------------------------------------------------------------------------
def tame_resolved():
    rc, out, _ = run(["systemctl", "is-active", "systemd-resolved"], quiet=True)
    if out.strip() != "active":
        print("[resolved] systemd-resolved not active; nothing to do.")
        return
    print("[resolved] systemd-resolved is active and may hold 127.0.0.53:53.")
    print("[resolved] Setting DNSStubListener=no so it does not squat on :53.")
    conf_dir = "/etc/systemd/resolved.conf.d"
    os.makedirs(conf_dir, exist_ok=True)
    with open(os.path.join(conf_dir, "99-serveros-lab.conf"), "w",
              newline="\n") as fh:
        fh.write("[Resolve]\nDNSStubListener=no\n")
    run(["systemctl", "restart", "systemd-resolved"])
    print("[resolved] Done. This is environment plumbing, not part of the "
          "grade.")


# ---------------------------------------------------------------------------
# Building / tearing down the wire
# ---------------------------------------------------------------------------
def _ns_exists(ns):
    rc, out, _ = run(["ip", "netns", "list"], quiet=True)
    return any(line.split()[0] == ns for line in out.splitlines() if line.strip())


def build_segment(ns, lan, cli, dns_ip, netmask_bits=24):
    """Create one veth pair: <lan> in root, <cli> in namespace <ns> with NO
    address. Idempotent-ish: tears down a prior copy of the same names first."""
    # Clean any stale copies so re-running is safe.
    run(["ip", "netns", "del", ns], quiet=True)
    run(["ip", "link", "del", lan], quiet=True)

    run(["ip", "netns", "add", ns], check=True)
    run(["ip", "link", "add", lan, "type", "veth", "peer", "name", cli],
        check=True)
    run(["ip", "link", "set", cli, "netns", ns], check=True)

    # Root side gets the DNS server address; this is where the student binds
    # BIND and dhcpd. The student is told to serve on lan0.
    run(["ip", "addr", "add", "%s/%d" % (dns_ip, netmask_bits), "dev", lan],
        check=True)
    run(["ip", "link", "set", lan, "up"], check=True)

    # Client side is brought UP but deliberately has NO address.
    run(["ip", "netns", "exec", ns, "ip", "link", "set", "lo", "up"])
    run(["ip", "netns", "exec", ns, "ip", "link", "set", cli, "up"], check=True)
    print("[wire] built %s (root) <-> %s (ns:%s, no address)" % (lan, cli, ns))


def teardown():
    for ns in (NS, NS2):
        run(["ip", "netns", "del", ns], quiet=True)
    for lan in (LAN0, LAN1):
        run(["ip", "link", "del", lan], quiet=True)
    print("[wire] torn down.")


def status():
    print("=== namespaces ===")
    run(["ip", "netns", "list"])
    for lan in (LAN0, LAN1):
        print("=== %s ===" % lan)
        run(["ip", "addr", "show", "dev", lan], quiet=False)
    for ns in (NS, NS2):
        if _ns_exists(ns):
            print("=== ns %s ===" % ns)
            run(["ip", "netns", "exec", ns, "ip", "addr"])


def install_packages():
    print("[install] installing client + diagnostic tools...")
    run(["apt-get", "update", "-qq"])
    run(["apt-get", "install", "-y",
         "dhcpcd-base", "dnsutils", "iproute2", "iptables"])


# ---------------------------------------------------------------------------
# SELF TEST -- the important part for you, since I cannot run this here.
# Verifies each capability on the real playground and reports pass/fail.
# ---------------------------------------------------------------------------
def selftest(dns_ip):
    print("=" * 60)
    print(" setup_lab_net.py self-test")
    print("=" * 60)
    ok = True

    def step(name, cond, detail=""):
        nonlocal ok
        mark = "PASS" if cond else "FAIL"
        if not cond:
            ok = False
        print("  [%s] %s%s" % (mark, name, ("  -- " + detail) if detail else ""))
        return cond

    # 1. root
    step("running as root", os.geteuid() == 0,
         "re-run with sudo if this fails")

    # 2. ip command present
    rc, _, _ = run(["ip", "-V"], quiet=True)
    if not step("iproute2 present (ip command)", rc == 0,
                "apt-get install -y iproute2"):
        print("\nCannot continue without iproute2.")
        return 1

    # 3. THE BIG ONE: can we create a network namespace at all?
    rc, _, err = run(["ip", "netns", "add", "servos_probe"], quiet=True)
    netns_ok = (rc == 0)
    step("kernel/host allows 'ip netns' (network namespaces)", netns_ok,
         "if this FAILS, this playground image cannot run the lab -- the whole "
         "design depends on namespaces. Tell your image maintainer, or switch "
         "to a KillerCoda track that permits netns.")
    if netns_ok:
        run(["ip", "netns", "del", "servos_probe"], quiet=True)
    else:
        print("\nStopping: without network namespaces nothing else works.")
        print("Error was:\n" + err)
        return 1

    # 4. can we make a veth pair?
    rc, _, _ = run(["ip", "link", "add", "spv0", "type", "veth",
                    "peer", "name", "spv1"], quiet=True)
    step("can create veth pairs", rc == 0)
    run(["ip", "link", "del", "spv0"], quiet=True)

    # 5. build a throwaway segment and prove the client end can reach the root
    print("  building a throwaway segment to test end-to-end reachability...")
    try:
        build_segment("servos_probe_ns", "splan", "spcli", dns_ip)
        # give the client end a temporary address in the same /24 and ping root
        run(["ip", "netns", "exec", "servos_probe_ns", "ip", "addr", "add",
             _sibling_ip(dns_ip) + "/24", "dev", "spcli"], quiet=True)
        rc, out, _ = run(["ip", "netns", "exec", "servos_probe_ns",
                          "ping", "-c", "1", "-W", "2", dns_ip], quiet=True)
        step("client namespace can reach the root-side address", rc == 0,
             "veth pair carries traffic")
    finally:
        run(["ip", "netns", "del", "servos_probe_ns"], quiet=True)
        run(["ip", "link", "del", "splan"], quiet=True)

    # 6. dhclient present (needed by the grader)
    rc, _, _ = run(["which", "dhcpcd"], quiet=True)
    step("dhcpcd present (the DHCP client this image uses to grade a lease)",
         rc == 0, "run with --install (installs dhcpcd-base)")

    # 7. dig present
    rc, _, _ = run(["which", "dig"], quiet=True)
    step("dig present (needed for DNS probes)", rc == 0, "run with --install")

    print("=" * 60)
    print(" self-test %s" % ("PASSED -- the playground can run the lab"
                             if ok else "FAILED -- see the FAIL lines above"))
    print("=" * 60)
    return 0 if ok else 1


def _sibling_ip(ip):
    """Return an address in the same /24 as ip, differing in the last octet, to
    use as a temporary client-side test address."""
    a, b, c, d = ip.split(".")
    d2 = "250" if d != "250" else "249"
    return "%s.%s.%s.%s" % (a, b, c, d2)


def main():
    ap = argparse.ArgumentParser(description="Build the Server OS lab wire.")
    ap.add_argument("--group", help="group id (for the DNS server address)")
    ap.add_argument("--phase", choices=["build", "change"], default="build",
                    help="'change' also builds the Part 5 second subnet")
    ap.add_argument("--install", action="store_true",
                    help="apt-get the client + diagnostic tools")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--teardown", action="store_true")
    ap.add_argument("--selftest", action="store_true",
                    help="verify this playground can run the lab, then clean up")
    args = ap.parse_args()

    if args.status:
        status()
        return
    if args.teardown:
        require_root()
        teardown()
        return

    require_root()

    # Resolve the group's addresses.
    dns_ip = None
    if args.group:
        from params import group_params
        p = group_params(args.group)
        dns_ip = p["dns_ip"]
        dns_ip2 = p["dns_ip2"]

    if args.selftest:
        # Use a harmless default address if no group supplied.
        return sys.exit(selftest(dns_ip or "192.168.99.10"))

    if args.install:
        install_packages()
        tame_resolved()

    if not args.group:
        print("ERROR: --group is required to build the wire (need the address).",
              file=sys.stderr)
        sys.exit(2)

    build_segment(NS, LAN0, CLI0, dns_ip)
    if args.phase == "change":
        build_segment(NS2, LAN1, CLI1, dns_ip2)
    print("\n[done] Wire is up. The student serves BIND + dhcpd on %s." % LAN0)
    print("       Grade with:  python3 check_lab.py --phase %s --group %s"
          % (args.phase, args.group))


if __name__ == "__main__":
    main()
