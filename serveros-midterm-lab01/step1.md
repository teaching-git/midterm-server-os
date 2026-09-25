# Find and Fix the Faults

The environment is already running: the company's DNS + DHCP services are up
(and broken), and a test client is waiting on the network. Your job is to make
a machine joining this network able to resolve the company's own host names.

## Check your progress
Run the checker. Its messages say what it observed and what it expected -- use
them as clues, and work from each symptom to its cause.

```
python3 /root/grading/check_lab.py --group lab01 --phase build
```

Fix the faults in the real configuration (`/etc/bind/`, `/etc/dhcp/`,
`/etc/default/isc-dhcp-server`, and remember faults are not always in a config
file). After each change, restart the affected service and re-run the checker.

Note: `dig @127.0.0.1` proves almost nothing -- the checker tests from the
client's point of view, and so should you.

## Record your work
Work inside a recorded session so your process is part of your evidence, and
keep an incident log of how you found and proved each fault:
```
script -a /root/session.log
```

When your score is as high as you can get it, submit to your group repository
as described in the midterm handout.
