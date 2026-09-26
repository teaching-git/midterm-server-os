#!/bin/bash
iptables -I INPUT -p udp --dport 53 -j DROP 2>/dev/null || true
