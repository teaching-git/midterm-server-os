# Lab 01 -- Company Network (novapeak)

This environment is a company's DNS + DHCP setup that is CURRENTLY BROKEN in
several ways. Your job is to find the faults, prove them with evidence, fix
them, and document what you did.

## Start
```
cd lab01        # (or wherever this folder landed)
bash setup.sh   # stages the environment and starts the services
```

## Your goal
A machine joining this company network with NO manual configuration must be
able to resolve the company's own host names. Right now it cannot. Find out why.

## Check your progress
```
python3 /root/grading/setup_lab_net.py --group lab01   # build the test wire (once)
python3 /root/grading/check_lab.py --group lab01 --phase build
```
The checker's messages tell you what was observed and what was expected -- use
them as clues. `dig @127.0.0.1` proves almost nothing; test from the client.

## What to hand in (see the midterm handout for full detail)
  - your fixed configuration
  - FINDINGS / incident log: how you found and proved each fault
  - your recorded shell session (work inside: script -a ~/session.log)

Note: you are root, so you can read the tooling in /root/grading. Reading it
tells you WHAT is checked; it does not find or fix the faults for you, and the
marks are for your evidence.
