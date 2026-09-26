# Submission Structure -- Server OS Midterm

Your group submits by pushing to your own GitHub repository. Your repository
**must** follow this exact structure. Marks depend partly on it being correct
and complete.

## Required repository layout

```
your-group-repo/
  README.md              # this file, completed with your group info (below)
  fixed-configs/         # copies of the configuration you repaired
    named.conf.options
    named.conf.local
    db.<company>          # your fixed forward zone
    db.<company>.rev      # your fixed reverse zone
    dhcpd.conf
    isc-dhcp-server       # the /etc/default/ file
  INCIDENT_LOG.md        # how you found and proved each fault (Part 2)
  AI_CRITIQUE.md         # AI declaration + comparison + verdict (Part 3)
  session.log            # your recorded shell session (script -a)
```

Templates for `INCIDENT_LOG.md` and `AI_CRITIQUE.md` are provided in this
handout folder -- copy them into your repo and fill them in. Do not invent your
own format; use the templates.

## Fill in your group information at the top of your repo README

- Group name / number:
- Members (name + GitHub username, one per line):
- Company / domain you were assigned:
- Group id used with the checker:

## How to collect your fixed configs

After you have repaired everything and the checker score is as high as you can
get it, copy the real files into your repo's `fixed-configs/`:

```
mkdir -p fixed-configs
cp /etc/bind/named.conf.options fixed-configs/
cp /etc/bind/named.conf.local   fixed-configs/
cp /etc/bind/db.*               fixed-configs/
cp /etc/dhcp/dhcpd.conf         fixed-configs/
cp /etc/default/isc-dhcp-server fixed-configs/
```

## How the checker score is captured

Run the checker and save its output into your repo so your Part 1 result is
recorded:

```
python3 /root/grading/check_lab.py --group lab01 --phase build | tee checker_result.txt
```

Commit `checker_result.txt` too.

## Commit discipline

- Commit as you go, not all at once at the end.
- Each member commits their own work under their own git identity.
- Clear commit messages ("fix reverse zone PTR", "add incident log entry for
  the firewall fault") -- not "update".
