# Find and Fix the Faults

Your working files are in `/root/lab`, and the live configuration is in the
usual places (`/etc/bind/`, `/etc/dhcp/`, `/etc/default/isc-dhcp-server`).

**The goal:** a machine joining this company network with no manual
configuration must be able to resolve the company's own host names. Right now
it cannot. Find out why.

## Build the test wire (once)
```
python3 /root/grading/setup_lab_net.py --group lab01
```

## Check your progress -- use the messages as clues
```
python3 /root/grading/check_lab.py --group lab01 --phase build
```
The checker says what it observed and what it expected. Work from the symptom
to the cause. Note: `dig @127.0.0.1` proves almost nothing -- test from the
client namespace as the checker does.

## Record your work
Do your work inside a recorded shell session so your process is evidence:
```
script -a /root/session.log
```
Keep an incident log of how you found and proved each fault (see the handout).
