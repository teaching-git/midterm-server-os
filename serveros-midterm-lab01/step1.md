# Find and Fix the Faults

The goal: a machine joining this network with no manual configuration must be
able to resolve the company's own host names. Right now it cannot. Find out why.

Build the test wire once, then check your progress. Use the checker's messages
as clues -- they say what was observed and what was expected.

```
python3 /root/grading/setup_lab_net.py --group lab01
```
```
python3 /root/grading/check_lab.py --group lab01 --phase build
```

Work inside a recorded session so your process is evidence, and keep an
incident log of how you found and proved each fault:
```
script -a /root/session.log
```

When your score is as high as you can get it, submit to your group repo as the
handout describes.
